#!/usr/bin/env python3
"""
webpanel.py - kleines Bedienpanel fuer iPad/Handy (im selben WLAN): http://<IP-des-Pi>:<Port>/

Szenen, Licht-Mix, Bewegungen, Farben, Tempo, Master, Strobe-Erlaubnis,
BLACKOUT, BLINDER bzw. SONNENBRILLE (alles hell) und AUTO (zurueck zur Musiksteuerung).
Bereich "Lichtstrahl": SMOKE (Nebelschub), FREEZE (Licht und Bewegung einfrieren),
BLITZ (Strobe auf Knopfdruck, Tempo per Regler), General Dimmer (= Master).
Beat-Lamperl blinkt im erkannten Takt. Kopfzeile: Erreichbarkeit (OLA, Effektband, Couchtisch, Theke) und Anzeige DROP / AUFBAU / STILLE.
WOW! (Taster: aufbauender Strobo-Effekt im BPM-Takt, nur solange gedrueckt; loslassen = Drop).
Es gibt KEINE Anmeldung: nur im vertrauenswuerdigen Heimnetz benutzen.
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from urllib.parse import parse_qs, unquote, urlparse

import health
from scenes import MIX_BUTTONS, PAGES

# Beschriftungen (Deutsch/English) stehen in texts.py; eigene Texte aus der Uebersetzungstabelle in texts.json.
from texts import AIMS, COLORS, MIX_PANEL, MOVES, SPEEDS, STYLE_BTNS, catalog  # noqa: E402,F401
from genre_style import STYLES  # noqa: E402

FONT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "inter.woff2")   # Inter (SIL OFL)

PAGE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Light-Butler</title><link rel="icon" type="image/svg+xml" href="/icon.svg"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="apple-mobile-web-app-title" content="Light-Butler"><meta name="theme-color" content="#16171f">
<style>
:root{color-scheme:dark}
@font-face{font-family:Inter;src:url(/static/inter.woff2) format("woff2");font-weight:100 900;font-display:swap}   /* vom Pi, kein Internet noetig */
body{margin:0;background:#12131c;color:#eee;font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;padding:10px}
button,input,select,textarea{font-family:inherit}   /* Knoepfe uebernehmen die Schrift (sonst Arial des Browsers) */
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#8ad;margin:14px 0 6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:6px}
button{background:#2a2c3d;color:#eee;border:0;border-radius:10px;padding:14px 4px;font-size:14px;font-weight:600;min-height:50px}
button:active{background:#4a4f78}.on{background:#e8710a;color:#fff}
.big{font-size:16px;min-height:62px;font-weight:600}
/* grosse Knoepfe oben: eigener Hintergrund je Funktion; aktiv = oranger Leuchtrahmen */
.big.on.bigfx,.big.on.sun,.big.on.auto{box-shadow:inset 0 0 0 3px #e8710a,0 0 12px #e8710a}
.halo{color:#fff;text-shadow:0 0 3px #000,0 0 3px #000,0 0 6px #000}
#b_blitz{background:repeating-linear-gradient(90deg,#f2f2f2 0 9px,#111 9px 18px)}
#b_blitz.on{background:repeating-linear-gradient(90deg,#fff 0 9px,#000 9px 18px);animation:zebra .25s linear infinite}
@keyframes zebra{from{background-position:0 0}to{background-position:18px 0}}
#b_fog{background:radial-gradient(ellipse at 25% 35%,rgba(225,230,236,.55),transparent 55%),radial-gradient(ellipse at 78% 70%,rgba(195,202,210,.5),transparent 60%),linear-gradient(180deg,#6d757e,#474e55);color:#fff;text-shadow:0 1px 3px rgba(0,0,0,.6)}
#b_fog.on{background:radial-gradient(ellipse at 30% 40%,rgba(240,243,246,.75),transparent 60%),radial-gradient(ellipse at 70% 65%,rgba(215,220,226,.7),transparent 62%),linear-gradient(180deg,#9aa2ab,#6b737b);background-size:200% 100%;animation:fogdrift 3s ease-in-out infinite alternate}
@keyframes fogdrift{from{background-position:0 0}to{background-position:100% 0}}
#b_fog{position:relative;overflow:hidden}#b_fog small{display:block;font-size:11px;font-weight:600;margin-top:2px;letter-spacing:0;text-shadow:none}
#b_fog .fdot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#3ddc6a;margin-right:4px;vertical-align:1px}
#b_fog .fbar{position:absolute;left:0;bottom:0;height:4px;background:#e8890a;width:0;transition:width .4s linear}
#b_fog.fst-off{background:linear-gradient(180deg,#3b3e46,#2a2c32);color:#aab}
#b_fog.fst-heat{animation:fogheat 1.4s ease-in-out infinite}@keyframes fogheat{0%,100%{box-shadow:inset 0 0 0 3px #e8890a}50%{box-shadow:inset 0 0 0 3px rgba(232,137,10,.3)}}
#b_fog.fst-pause{filter:brightness(.62)}#b_fog.fst-pause .fbar{background:#9aa2ab}
#b_fog.fst-err{box-shadow:inset 0 0 0 3px #e03a3a}
#fognote{display:flex;align-items:center;gap:10px;margin:0 0 8px;padding:6px 10px;border-radius:8px;font-size:13px;font-weight:600;background:#4a3a08;color:#ffd96a;border:1px solid #8a6d12}
#fognote.off{background:#123a1f;color:#8af0a8;border-color:#1f6b38}#fognote span{flex:1}#fognote button{flex:none;min-height:30px;padding:4px 14px;font-size:13px}
#b_black{background:#08080a;color:#7a7e8a;border:1px solid #262833}
#b_black.on{background:#000;color:#e8710a;border-color:#000}
#b_build{background:linear-gradient(90deg,#0b0b0e 0%,#34363d 30%,#8f939e 62%,#e9ebf0 85%,#fff 100%)}
#b_build.on{background:linear-gradient(90deg,#2a2b30 0%,#7b7f8a 30%,#d4d7de 60%,#fff 80%);background-size:160% 100%;animation:wowup .6s ease-in-out infinite alternate}
@keyframes wowup{from{background-position:100% 0}to{background-position:0 0}}
#b_freeze{position:relative;overflow:hidden;background:linear-gradient(160deg,#e6f7ff 0%,#a3daf6 45%,#4c9fd2 100%);color:#0b3550;text-shadow:0 1px 0 rgba(255,255,255,.6)}
#b_freeze::before{content:"❄";position:absolute;left:5px;top:2px;font-size:15px;line-height:1;color:rgba(255,255,255,.95);text-shadow:0 0 3px #4c9fd2;pointer-events:none}
#b_freeze::after{content:"❄";position:absolute;right:5px;bottom:3px;font-size:21px;line-height:1;color:rgba(255,255,255,.8);text-shadow:0 0 3px #4c9fd2;pointer-events:none}
#b_freeze.on{background:linear-gradient(160deg,#fff 0%,#cdeeff 45%,#7cc8f0 100%);box-shadow:inset 0 0 0 3px #e8710a,0 0 14px #7fd3ff}
.sun{background:#d9c400;color:#222;position:relative;overflow:hidden}.sun.on{background:#fff}
#b_sun::after{content:"🕶";position:absolute;right:4px;bottom:2px;font-size:20px;line-height:1;pointer-events:none}
.cb{text-shadow:0 1px 2px rgba(0,0,0,.55);font-weight:600}.cb.on{box-shadow:inset 0 0 0 3px #e8710a,0 0 12px #e8710a;font-weight:800}
#color{grid-template-columns:repeat(11,minmax(0,1fr));gap:4px}#color button{min-width:0;padding:10px 2px;font-size:12px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}   /* alle 11 Farben in einer Zeile */
@media(max-width:520px){#color{gap:3px}#color button{font-size:0;padding:0;min-height:40px;border-radius:7px}#color button.on{box-shadow:inset 0 0 0 3px #e8710a}
 #color button::after{font-size:11px;font-weight:800}#color button[data-v="auto"]::after{content:"A"}#color button[data-v="white"]::after{content:"W"}#color button[data-v="uv"]::after{content:"UV"}}   /* Handy: nur Farbflaechen, Kuerzel fuer Auto, Weiss, UV */
.auto{background:#1c7a3a}.auto.on{background:#27b552}
#ev{display:none;text-align:center;font-size:30px;font-weight:800;letter-spacing:.12em;padding:12px;border-radius:12px;margin-bottom:8px}
#ev.drop{display:block;background:#e8110a;color:#fff;animation:bl .3s infinite alternate}
#ev.build{display:block;background:#e8710a;color:#fff;font-size:22px}
#ev.gap{display:block;background:#000;color:#fff;border:2px solid #e8710a;font-size:22px}
@keyframes bl{from{opacity:1}to{opacity:.55}}
#beatrow{display:flex;align-items:center;gap:10px;margin-bottom:6px;font-size:13px;color:#aab}
#beat{display:inline-block;width:32px;height:32px;border-radius:50%;background:#fff;box-shadow:0 0 16px #fff;opacity:.12}
#setbar{display:flex;gap:10px;align-items:center;margin-bottom:6px}#setbar button{min-height:40px;padding:8px 12px}#setnote{font-size:12px;color:#889}
details.sg{background:#181a22;border-radius:10px;margin:6px 0;overflow:hidden}details.sg>summary{padding:12px;font-weight:700;cursor:pointer}
.srow{padding:8px 12px 10px;border-top:1px solid #262a36}.srow.mod .sname{color:#f0a030}
.sname{font-weight:600}.sdesc{font-size:12px;color:#99a;margin:2px 0 6px;line-height:1.35}
.sctl{display:flex;align-items:center;gap:8px}.sctl input[type=range]{flex:1;min-width:0}
.sctl input[type=number]{width:74px;background:#222536;color:#eee;border:1px solid #3a3f58;border-radius:6px;padding:6px;font-size:14px}
.txrow{display:grid;grid-template-columns:1fr 1fr auto;gap:6px;align-items:center;margin:3px 0}.txrow input{background:#222536;color:#eee;border:1px solid #3a3f58;border-radius:6px;padding:7px;font-size:14px;min-width:0;width:100%;box-sizing:border-box}
.txrow.mod input{border-color:#f0a030}.txrow .sres{min-height:34px!important}.txcat{font-size:12px;color:#8ad;letter-spacing:.06em;text-transform:uppercase;margin:12px 0 2px}.txhd{display:grid;grid-template-columns:1fr 1fr 34px;gap:6px;font-size:12px;color:#889}
#speed button{background:linear-gradient(90deg,#1d5fd8 0%,#2f80e0 26%,#e8890a 42%,#ef8a10 58%,#e0451a 76%,#d61e1e 100%);background-size:300% 100%;color:#fff;font-weight:600;text-shadow:0 1px 3px rgba(0,0,0,.6)}
#speed button:nth-child(2){background-position:0% 0}#speed button:nth-child(3){background-position:50% 0}#speed button:nth-child(4){background-position:100% 0}
#speed button[data-v="auto"]{background:linear-gradient(90deg,#1c7a3a,#2b8a4a);color:#fff}
#spst{display:grid;grid-template-columns:1fr 2fr;gap:0 12px}#speed{grid-template-columns:repeat(4,minmax(0,1fr))}#style{grid-template-columns:repeat(6,minmax(0,1fr))}
#spst .grid{gap:4px}#spst button{min-height:44px;padding:4px 1px;font-size:12px}
#style button{background:linear-gradient(90deg,#1c7a3a,#2b8a4a);color:#fff;font-weight:600;text-shadow:0 1px 3px rgba(0,0,0,.7)}
#style button.on{box-shadow:inset 0 0 0 3px #e8710a,0 0 12px #e8710a}#style button.eff{box-shadow:inset 0 0 0 2px #fff}   /* Auto: Stil aus Mixxx weiss umrandet */
#speed button.on{box-shadow:inset 0 0 0 3px #e8710a,0 0 12px #e8710a}
#ebgrid button{position:relative;font-size:14px}#ebgrid .ebn{display:block;font-size:10px;color:#99a;font-weight:400}#ebgrid .ebsnd{color:#7ec8ff;font-weight:700}
#ebgrid button.ebauto{background:linear-gradient(90deg,#1c7a3a,#2b8a4a);color:#fff;font-weight:700}#ebgrid button.on{box-shadow:inset 0 0 0 3px #e8710a,0 0 12px #e8710a}
#ebgrid button.cur{box-shadow:inset 0 0 0 2px #7dffa0}#ebgrid button:disabled{opacity:.35}
#ebgrid button.sauto::after{content:"AUTO";position:absolute;top:3px;right:5px;font-size:9px;font-weight:700;color:#7dffa0;letter-spacing:.5px}
#scenegrid button.sauto{position:relative}#scenegrid button.sauto::after{content:"AUTO";position:absolute;top:3px;right:5px;font-size:9px;font-weight:700;color:#7dffa0;letter-spacing:.5px}
#beam .bcell{background:#1d2030;border-radius:10px;padding:8px 10px;display:flex;flex-direction:column;justify-content:center;gap:6px;transition:opacity .3s}
#beam .bcell label{display:flex;justify-content:space-between;font-size:13px;color:#bbc}#beam .bcell b{color:#eee;font-variant-numeric:tabular-nums}
#beam .bcell input{width:100%}#beam select{background:#222536;color:#eee;border:1px solid #3a3f58;border-radius:6px;padding:6px;font-size:15px;width:100%}
#beam button{background:linear-gradient(90deg,#1c7a3a,#2b8a4a);color:#fff;font-weight:700}#beam button.on{box-shadow:inset 0 0 0 3px #e8710a,0 0 12px #e8710a}
#beam.bauto .bcell{opacity:.55}
#beam button.on{box-shadow:inset 0 0 0 3px #e8710a,0 0 12px #e8710a}   /* Auto gewaehlt: orange wie AUTO oben */
#b_auto,#beam button{background:linear-gradient(90deg,#1c7a3a,#2b8a4a)!important;color:#fff;font-weight:600;text-shadow:0 1px 3px rgba(0,0,0,.6)}   /* alle Auto-Knoepfe gleich; gewaehlt = oranger Rahmen */
/* Licht-Mix: gedaempfte Hintergruende mit schlichtem Zeichen; Bewegung nur, solange der Knopf aktiv ist */
.fine{display:grid;grid-template-columns:repeat(4,1fr);gap:4px 12px;margin:8px 2px 4px;transition:opacity .3s}
.fine.off{opacity:.45}.fine label{display:flex;justify-content:space-between;font-size:13px;color:#bbc}.fine label b{color:#eee;font-variant-numeric:tabular-nums}
.fine input{width:100%}
@media(max-width:560px){.fine{grid-template-columns:repeat(2,1fr)}}
#mix button,#move button{position:relative;overflow:hidden;isolation:isolate;color:#eef;text-shadow:0 1px 3px rgba(0,0,0,.8)}
#mix button::before,#mix button::after,#move button::after{position:absolute;pointer-events:none;z-index:-1}
#mix button::after,#move button::after{right:7px;bottom:3px;font-size:20px;line-height:1;color:rgba(255,255,255,.45)}
#mix button.on,#move button.on{box-shadow:inset 0 0 0 3px #e8710a,0 0 12px #e8710a}   /* gewaehlt: ueberall orange umrandet wie AUTO oben */
#mix button[data-v="Discokugel"]{background:radial-gradient(circle at 18% 30%,#c06a8a 0 2px,transparent 3px),radial-gradient(circle at 42% 70%,#6a8ac0 0 2px,transparent 3px),radial-gradient(circle at 68% 25%,#c0b06a 0 2px,transparent 3px),radial-gradient(circle at 85% 65%,#6ac09a 0 2px,transparent 3px),radial-gradient(circle at 55% 45%,#a06ac0 0 2px,transparent 3px),#24222e}
#mix button[data-v="Discokugel"]::after{content:"✺"}
#mix button[data-v="Discokugel"].on{animation:disco .7s steps(2) infinite}
@keyframes disco{50%{filter:brightness(1.7) hue-rotate(90deg)}}
#mix button[data-v="Karussell"]{background:#262633}
#mix button[data-v="Karussell"]::before{content:"";inset:-60%;background:conic-gradient(#7a4a5a,#7a6a44,#4a7a5a,#44607a,#5e4a7a,#7a4a5a);opacity:.55}
#mix button[data-v="Karussell"]::after{content:"↻"}
#mix button[data-v="Karussell"].on::before{animation:spin 3s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#mix button[data-v="Sternenhimmel"]{background:linear-gradient(180deg,#141a33,#232b4a)}
#mix button[data-v="Sternenhimmel"]::before{content:"";inset:0;background:radial-gradient(circle at 15% 25%,#fff 0 1px,transparent 2px),radial-gradient(circle at 35% 70%,#cfd8ff 0 1px,transparent 2px),radial-gradient(circle at 60% 35%,#fff 0 1px,transparent 2px),radial-gradient(circle at 80% 75%,#dfe6ff 0 1px,transparent 2px),radial-gradient(circle at 90% 20%,#fff 0 1px,transparent 2px);opacity:.7}
#mix button[data-v="Sternenhimmel"]::after{content:"✦"}
#mix button[data-v="Sternenhimmel"].on::before{animation:twinkle 1.4s ease-in-out infinite alternate}
@keyframes twinkle{from{opacity:.2}to{opacity:1}}
#mix button[data-v="STOP"]{background:#3c3f48}
#mix button[data-v="STOP"]::after{content:"■";font-size:15px;bottom:5px}
#mix button[data-v="nach aussen"]{background:#26283a}
#mix button[data-v="nach aussen"]::before,#mix button[data-v="nach innen"]::before{content:"";inset:0;background:radial-gradient(ellipse at center,rgba(150,170,220,.55),transparent 60%)}
#mix button[data-v="nach aussen"]::after{content:"↤ ↦";font-size:16px}
#mix button[data-v="nach aussen"].on::before{animation:chaseout 1.1s ease-out infinite}
@keyframes chaseout{from{transform:scaleX(.2);opacity:1}to{transform:scaleX(2.2);opacity:0}}
#mix button[data-v="nach innen"]{background:radial-gradient(ellipse at center,#22243a 30%,#3a4466)}
#mix button[data-v="nach innen"]::after{content:"↦ ↤";font-size:16px}
#mix button[data-v="nach innen"].on::before{animation:chasein 1.1s ease-in infinite}
@keyframes chasein{from{transform:scaleX(2.2);opacity:0}to{transform:scaleX(.2);opacity:1}}
#mix button[data-v="Scanner"]{background:#151418}
#mix button[data-v="Scanner"]::before{content:"";bottom:7px;height:5px;left:35%;width:30%;border-radius:3px;background:radial-gradient(ellipse at center,#e0402e,rgba(150,30,20,.25) 70%,transparent);box-shadow:0 0 8px rgba(210,58,42,.6)}
#mix button[data-v="Scanner"].on::before{animation:scanner 1.2s ease-in-out infinite alternate}
@keyframes scanner{from{left:2%}to{left:68%}}
#mix button[data-v="Regenbogen"]{background:linear-gradient(90deg,#7a3a3a,#7a5a34,#76703a,#3e6e48,#3a6470,#3e4a7a,#5e407a,#7a3a3a);background-size:200% 100%}
#mix button[data-v="Regenbogen"].on{animation:rainbow 4s linear infinite}
@keyframes rainbow{to{background-position:200% 0}}
/* Bewegung: dunkel mit Zeichen fuer die Richtung; das Zeichen bewegt sich, solange der Knopf aktiv ist */
#move button{background:#2a2c3d}#move button.on{background:#3a3e58}
#move button::after{font-size:24px;color:rgba(160,190,255,.35)}
#move button[data-v="duck"]::after{content:"〰"}
#move button[data-v="home"]::after{content:"⊙"}
#move button[data-v="random"]::after{content:"⁂"}
#move button[data-v="sweep"]::after{content:"⌒"}
#move button[data-v="circle"]::after{content:"↻"}
#move button[data-v="vertical"]::after{content:"↔";transform:rotate(90deg)}
#move button[data-v="horizontal"]::after{content:"↔"}
#move button[data-v="fan"]::after{content:"≋"}
#move button.on::after{color:rgba(190,215,255,.75)}
#move button[data-v="duck"].on::after{animation:float 1.6s ease-in-out infinite alternate}
@keyframes float{from{transform:rotate(-10deg) translateY(1px)}to{transform:rotate(10deg) translateY(-2px)}}
#move button[data-v="random"].on::after{animation:jump 1.2s steps(1) infinite}
@keyframes jump{0%{transform:translate(0,0)}25%{transform:translate(-14px,-6px)}50%{transform:translate(-4px,-12px)}75%{transform:translate(-20px,-2px)}}
#move button[data-v="sweep"].on::after{animation:sweep 1.4s ease-in-out infinite alternate}
@keyframes sweep{from{transform:translateX(-40px)}to{transform:translateX(0)}}
#move button[data-v="circle"].on::after{animation:spin 2s linear infinite}
#move button[data-v="vertical"].on::after{animation:tilt 1s ease-in-out infinite alternate}
@keyframes tilt{from{transform:translateY(3px) rotate(90deg)}to{transform:translateY(-7px) rotate(90deg)}}
#move button[data-v="horizontal"].on::after{animation:pan 1s ease-in-out infinite alternate}
@keyframes pan{from{transform:translateX(0)}to{transform:translateX(-24px)}}
#move button[data-v="fan"].on::after{animation:swim 1.2s ease-in-out infinite alternate}
@keyframes swim{from{transform:translateX(0) scaleY(1)}to{transform:translateX(-12px) scaleY(.7)}}
#homebody .hrow{margin:4px 0 12px}#homebody .hlab{display:flex;justify-content:space-between;font-size:14px;color:#dde;margin-bottom:4px}#homebody .hlab b{color:#eee;font-variant-numeric:tabular-nums}
#homebody input[type=range]{width:100%}#homebody .grid button.on{background:#e8710a}#homebody .grid button.unr{opacity:.45}
#homebody .hst{display:block;font-size:11px;font-weight:400;color:#cdd;margin-top:2px}#homebody .herr{font-size:12px;color:#ff6b5a;margin-top:6px}
#homebody .hedit{margin-top:16px;border-top:1px solid #2a2e40;padding-top:8px}#homebody .hedit>summary{color:#8ad;font-weight:700;cursor:pointer;padding:4px 0}
#homebody .hed{display:flex;gap:6px;align-items:center;margin:4px 0}#homebody .hed input{flex:1;min-width:0;background:#222536;color:#eee;border:1px solid #3a3f58;border-radius:6px;padding:8px;font-size:15px}
#homebody .hed button{flex:0 0 auto;padding:8px 12px}#homebody .had{display:block;color:#889;font-size:11px;margin:0 0 8px 2px}
#homebody .hfn{flex:1;font-size:13px;color:#dde}#homebody .hfn small{display:block;color:#889;font-size:11px}#homebody .hfound{margin-top:8px;max-height:360px;overflow-y:auto}
.sunit{font-size:12px;color:#99a;min-width:34px}.sres{min-height:34px!important;padding:4px 10px!important;font-size:16px}
.sdef{font-size:11px;color:#778;margin-top:3px}
.schead{display:flex;justify-content:space-between;align-items:center;margin:14px 0 6px}.sedit{min-height:38px!important;padding:6px 14px!important}
.scnote{font-size:12px;color:#99a;margin-bottom:6px}
#scenegrid button.sel{outline:3px solid #3aa0ff;outline-offset:-3px}#scenegrid button.sadd{background:#1c7a3a;font-size:26px;font-weight:700}#aim button.sadd{background:#1c7a3a;font-weight:700}#aim_edit.on{background:#e8710a}
.sceditor{background:#181a22;border-radius:10px;margin:8px 0;padding:10px 12px}.sceditor .edt{font-weight:700;margin-bottom:8px;color:#8ad}
.sceditor label{display:block;font-size:13px;color:#aab;margin:8px 0 0}.sceditor label b{color:#eee;float:right}
.sceditor input[type=text],.sceditor select{width:100%;box-sizing:border-box;margin-top:3px;background:#222536;color:#eee;border:1px solid #3a3f58;border-radius:6px;padding:9px;font-size:15px}
.sceditor input[type=range]{width:100%;margin-top:4px}.sceditor .chk{display:flex;align-items:center;gap:8px;color:#dde}.sceditor .chk input{width:auto;margin:0}
.sceditor .klabel{font-size:13px;color:#aab;margin:10px 0 2px}.kinds{display:grid;grid-template-columns:1fr 1fr;gap:2px 10px}.kinds .klabel{grid-column:1/3}
.ebtn{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.ebtn button{flex:1 1 30%;min-height:44px;padding:8px}.ebtn .ok{background:#1c7a3a}.ebtn .del{background:#8a2a2a}
#audiobody select{width:100%;background:#222536;color:#eee;border:1px solid #3a3f58;border-radius:6px;padding:9px;font-size:15px;margin:4px 0 8px}
.meter{display:flex;gap:2px;height:26px;padding:3px;background:#11131c;border-radius:6px;margin:6px 0 2px}   /* LED-Kette wie am Mischpult (Wunsch 12.11.2026) */
.meter i{flex:1;border-radius:2px;background:#1b3123}.meter i.y{background:#3a3217}.meter i.r{background:#3d1a1a}
.meter i.on{background:#2ecc40}.meter i.y.on{background:#f0c040}.meter i.r.on{background:#ff3b30;box-shadow:0 0 6px #ff3b30}
.meter i.pk.y,.meter i.pk.r{animation:bl .25s infinite alternate}
.mnum{font-size:13px;color:#bbc;display:flex;justify-content:space-between}
.clipb{display:none;background:#ff3b30;color:#fff;font-weight:800;padding:3px 10px;border-radius:6px;margin-left:8px;animation:bl .4s infinite alternate}
.seg button{min-height:38px;padding:6px 10px;flex:1}.seg{display:flex;gap:6px;margin:4px 0 8px}
.fx{background:#181a22;border-radius:10px;margin:6px 0;overflow:hidden}
.fxh{display:flex;gap:10px;align-items:baseline;padding:11px 12px;cursor:pointer;user-select:none}
.fxh:active{background:#242736}
.fxn{font-weight:800;min-width:34px;color:#f0a030}.fxl{flex:1;font-weight:600}.fxa{font-size:13px;color:#9aa}
.fxb{padding:0 8px 10px}.fxb table{width:100%;border-collapse:collapse;font-size:14px}
.fxb th{text-align:left;font-size:12px;color:#889;font-weight:600;padding:4px 6px}
.fxb td{padding:5px 6px;border-top:1px solid #262a36;vertical-align:top}
.fxb small{color:#c8a050}
.fxb td.val{white-space:nowrap;min-width:110px}.vn{display:inline-block;width:34px;text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.bar{display:inline-block;width:56px;height:7px;background:#2a2e3c;border-radius:4px;margin-left:8px;vertical-align:middle;overflow:hidden}
.bar i{display:block;height:100%;width:0;background:#3aa0ff}
#mxline{font-size:13px;margin:2px 0 6px;color:#bbc}#mxline .mxn{color:#9fd0ff;font-weight:700}#mxline .mxs{color:#ffb86b;font-weight:700}
#reach{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;margin-bottom:6px}#reach a.cfgl{color:#9fd0ff;text-decoration:underline;text-underline-offset:2px}
#net{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:13px;margin-bottom:6px;color:#bbc}
#net .nb{white-space:nowrap}#net .mainc{font-size:10px;background:#2a3f6a;color:#cde;border-radius:4px;padding:1px 5px;margin-left:4px}
#net .sg{color:#2ecc40}#net .sm{color:#f0c040}#net .sw{color:#ff6b5a}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;background:#666;margin-right:5px;vertical-align:-1px}
.dot.ok{background:#2ecc40}.dot.bad{background:#ff3b30}
#st{font-size:13px;color:#aab;margin:6px 0;line-height:1.5}#note{color:#fc6}
input[type=range]{width:100%}
.ctlrow{display:flex;flex-wrap:wrap;gap:5px}
.ctlrow button{flex:1 1 auto;min-width:0;min-height:50px;padding:3px 3px;font-size:13px;line-height:1.2;font-weight:600;white-space:nowrap}
@media(max-width:400px){.ctlrow button{font-size:11px;padding:4px 2px}}
.blitzrow{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center;margin-top:6px}.blitzrow>button{flex:0 0 34%;font-size:15px}.blitzrow .bz{flex:0 1 auto;min-width:0}.bzl{font-size:13px;color:#aab;margin-bottom:2px}.bzl b{color:#eee}
a.sedit{text-decoration:none;display:inline-flex;align-items:center}
.fxf{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px 4px 10px}.fxf label{font-size:12px;color:#99a;display:flex;flex-direction:column;gap:3px}
.fxf label.wide{grid-column:1/3}.fxf input,.fxf select,.fxt input,.fxt select,.fxa2 input,.fxa2 select{background:#222536;color:#eee;border:1px solid #3a3f58;border-radius:6px;padding:8px;font-size:14px;min-width:0;width:100%;box-sizing:border-box}
.fxf .ebtn{grid-column:1/3;margin-top:2px}.fxf small{grid-column:1/3;color:#889}
.fxd{background:#222536;color:#eee;border:1px solid #3a3f58;border-radius:6px;padding:6px;font-size:13px;width:100%;box-sizing:border-box;resize:vertical;font-family:inherit;line-height:1.35}
.fxpend{background:#2a3f6a;border-radius:10px;padding:10px 12px;margin:6px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:14px}.fxpend button{min-height:38px;padding:6px 12px}
.fxtools{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}.fxtools button{flex:1 1 30%;min-height:42px;padding:8px}
.fxa2,.fxt{background:#181a22;border-radius:10px;padding:10px 12px;margin:8px 0}.fxa2 .row,.fxt .row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}.fxa2 label,.fxt label{font-size:12px;color:#99a;display:flex;flex-direction:column;gap:3px}
.fxt table{width:100%;border-collapse:collapse;font-size:13px}.fxt td{padding:3px 3px;vertical-align:top}.fxt th{font-size:11px;color:#889;text-align:left;padding:2px 3px}
.fxrm{background:#181a22;border-radius:10px;padding:8px 12px;margin:8px 0;font-size:14px}.fxrm div{display:flex;gap:8px;align-items:center;padding:4px 0}.fxrm span{flex:1}
#pwdlg{position:fixed;inset:0;z-index:90;background:#000b;align-items:center;justify-content:center;padding:16px}
#pwcard{background:#1b1d2a;border:1px solid #3a3f58;border-radius:14px;padding:16px;max-width:420px;width:100%;box-sizing:border-box}#pwtxt{font-size:15px;line-height:1.45;color:#eee}
#pwdev{display:flex;flex-direction:column;gap:6px}#pwdev .pwl{font-size:13px;color:#aab;margin-top:14px}#pwdev button{min-height:44px;padding:8px}
.pwb{display:flex;gap:8px;margin-top:16px}.pwb button{flex:1;min-height:48px;padding:8px}.pwb .pwgo{background:#8a2a2a;color:#fff}
#hdr{margin-bottom:8px;position:relative}
#b_auto.on{background:#e8710a!important}html.pilot .lk>*,html.pilot .lk .grid{pointer-events:none}html.pilot .lk button:not(.on):not(.sauto):not(.cur),html.pilot .lk input,html.pilot .lk select{opacity:.45}
.pbox{background:#1b1d2a;border-radius:12px;padding:12px;margin:8px 0}.pbox>h2:first-child,#pages>:first-child,#pages>:first-child>h2:first-child{margin-top:0}.pbox>:last-child{margin-bottom:0}
#stbox{padding:8px 12px;margin:8px 0 0}
@media(max-width:480px){body:not([class]){padding:10px 4px}.pbox{padding:10px 6px}#stbox{padding:6px}#row1{padding:0 6px}#spst{gap:0 8px}#speed{grid-template-columns:repeat(2,minmax(0,1fr))}#style{grid-template-columns:repeat(3,minmax(0,1fr))}#spst button{min-height:38px;font-size:11.5px}}
#beat,#bpmtxt{cursor:pointer}#bpmtxt{box-sizing:border-box;height:32px;border:1px solid #2a2e3c;border-radius:10px;padding:0 6px}   /* so hoch wie Statusfeld und Knoepfe */#bpmtxt:hover,#bpmtxt.open{border-color:#3a4560}
#tpop{position:absolute;left:0;top:50px;z-index:30;width:min(420px,100%);background:#232638;border:1px solid #3a3f58;border-radius:12px;padding:10px 14px 12px;box-shadow:0 8px 24px rgba(0,0,0,.5)}
#tpop .tph{display:flex;justify-content:space-between;align-items:baseline;font-size:13px;color:#ccd}#tpop .tph span{color:#889;font-size:12px}
#tpop .tpnow{margin:4px 0 8px;display:flex;align-items:baseline}#tpop .tpnow b{font-size:32px;color:#fff;font-variant-numeric:tabular-nums}#tpop .tpnow small{margin-left:8px;color:#ffb86b;font-size:12px}
#tpop .tpbtns{display:grid;grid-template-columns:1fr 1fr 1.3fr 1fr 1fr;gap:6px}#tpop .tpbtns button{min-height:40px;padding:4px;font-size:15px}#tpop .tpbtns #bpm_auto.on{background:#3c9a4c}
#tptap{width:100%;margin-top:8px;min-height:46px;background:#3a2f4a;color:#e3d0ff;font-weight:700;font-size:15px;touch-action:manipulation;user-select:none;-webkit-user-select:none}#tptap.hit{background:#5a4a78}
#tpop small{display:block;margin-top:8px;color:#889;font-size:11.5px}
#row1{display:flex;align-items:center;gap:10px;height:46px}
#powerbtn{flex:none;width:32px;height:32px;min-height:0;padding:0;border-radius:50%;background:#3a2226;color:#ff8a7a;font-size:15px;font-weight:800;display:flex;align-items:center;justify-content:center;border:1px solid #6a3a40}
#statbtn{flex:none;width:30px;height:30px;border-radius:50%;background:#2a2c3d;color:#9fd0ff;display:flex;align-items:center;justify-content:center;text-decoration:none;border:1px solid #3a3f58}
#evslot.smshow{background:#6b4bbf;color:#fff;border-color:#6b4bbf;font-size:20px;font-weight:800;letter-spacing:.06em}
#smbtn,#rmbtn,#dbbtn,#djbtn{flex:none;width:30px;height:30px;border-radius:50%;background:#2a2c3d;color:#9fd0ff;display:flex;align-items:center;justify-content:center;text-decoration:none;border:1px solid #3a3f58}@media(max-width:480px){#smbtn,#rmbtn,#dbbtn,#djbtn{display:none!important}}
#hlbtn{flex:none;width:30px;height:30px;border-radius:50%;background:#2a2c3d;color:#9fd0ff;display:flex;align-items:center;justify-content:center;text-decoration:none;border:1px solid #3a3f58;position:relative}@media(max-width:480px){#helpbtn{display:none!important}#evslot:not(.laser) #evtext{display:none}#row1 #evslot.laser{font-size:10px;line-height:1.05;letter-spacing:0;white-space:normal;text-align:center}}#hlbtn.warn{color:#f0c040}#hlbtn.crit{color:#ff5a4d}
#statsec{display:none}body.vstat #statsec{display:block}body.vstat>*:not(#statsec):not(#toast):not(script){display:none!important}
#presec{display:none}body.vpre #presec{display:block}body.vpre>*:not(#presec):not(#toast):not(script){display:none!important}
#hlsec{display:none}body.vhealth #hlsec{display:block}body.vhealth>*:not(#hlsec):not(#toast):not(script){display:none!important}
.stsec .stgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;margin-top:10px}
.stsec .stc{background:#1b1d2a;border-radius:12px;padding:12px 14px}.stsec h3{margin:0 0 10px;font-size:13px;color:#9fd0ff;text-transform:uppercase;letter-spacing:.06em}
.stsec .big{display:flex;flex-wrap:wrap;gap:6px 22px}.stsec .big div{display:flex;flex-direction:column}.stsec .big b{font-size:24px;color:#fff;font-variant-numeric:tabular-nums}.stsec .big span{font-size:12px;color:#99a}
.stsec .pbar{height:8px;border-radius:4px;background:#2a2c3d;overflow:hidden;margin:4px 0}.stsec .pbar i{display:block;height:100%;background:#2b8a4a}
.stsec .srow2{display:grid;grid-template-columns:22px 1fr auto;gap:2px 10px;align-items:center;margin:6px 0;font-size:14px}.stsec .chip{width:22px;height:14px;border-radius:4px}
.stsec .srow2 small{color:#99a;font-variant-numeric:tabular-nums}.stsec .cols{display:flex;align-items:flex-end;gap:4px;height:110px;margin-top:6px}
.stsec .cols div{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;font-size:10px;color:#99a}.stsec .cols i{display:block;width:100%;border-radius:3px 3px 0 0;min-height:1px}
.stsec table{width:100%;border-collapse:collapse;font-size:13px}.stsec td{padding:3px 4px;border-bottom:1px solid #262839}.stsec td.n{text-align:right;color:#bbc;font-variant-numeric:tabular-nums;white-space:nowrap}
#hlhead{border-radius:12px;padding:12px 14px;margin-top:8px;background:#1b1d2a;border-left:4px solid #555a70}#hlhead.ok{border-left-color:#2ecc40}#hlhead.warn{border-left-color:#f0c040}#hlhead.crit{border-left-color:#ff3b30}
#hlhead b{font-size:18px;color:#fff}#hlhead ul{margin:6px 0 2px;padding-left:18px;font-size:14px}#hlhead li.crit{color:#ff8a7e;font-weight:600}#hlhead small{display:block;color:#99a;margin-top:4px}
.stsec h3 .hb{float:right;font-size:11px;letter-spacing:0;text-transform:none;font-weight:700;border-radius:5px;padding:1px 7px;color:#10121a;background:#555a70}.stsec h3 .hb.ok{background:#2ecc40}.stsec h3 .hb.warn{background:#f0c040}.stsec h3 .hb.crit{background:#ff5a4d}
#hlbody .hr{display:flex;justify-content:space-between;gap:12px;font-size:13px;color:#99a;margin:5px 0}#hlbody .hr span:last-child{color:#dde;text-align:right;font-variant-numeric:tabular-nums}
#hlbody .core{display:grid;grid-template-columns:52px 1fr 42px;gap:8px;align-items:center;font-size:12px;color:#99a}#hlbody .core span:last-child{text-align:right;color:#dde;font-variant-numeric:tabular-nums}
#hlbody .sp{margin-top:8px;font-size:11px;color:#99a}#hlbody .sp svg{display:block;width:100%;height:48px;background:#161823;border-radius:4px;margin:2px 0}#hlbody .sp .ax{display:flex;justify-content:space-between}
.stsec .pl{max-height:420px;overflow:auto}.stsec .mxe{display:inline-block;font-size:9.5px;line-height:13px;font-weight:800;border-radius:4px;padding:0 4px;color:#fff}
#setbtn{flex:none;width:30px;height:30px;border-radius:50%;background:#2a2c3d;color:#b0b4c4;font-size:17px;display:flex;align-items:center;justify-content:center;text-decoration:none;border:1px solid #3a3f58}
#helpbtn{flex:none;width:30px;height:30px;min-height:0;padding:0;border-radius:50%;background:#2a2c3d;color:#9fd0ff;font-size:16px;font-weight:800;display:flex;align-items:center;justify-content:center;text-decoration:none;border:1px solid #3a3f58}
#row1 #beat{flex:none}
#bpmtxt{flex:none;min-width:84px;display:flex;align-items:center;white-space:nowrap;color:#aab;font-size:12px}#bpmtxt b{display:inline-block;width:3ch;text-align:right;font-size:24px;line-height:28px;color:#eee;margin-right:4px;font-variant-numeric:tabular-nums}
#bpmlab{display:flex;flex-direction:column;justify-content:flex-end;height:26px;line-height:12px}#bpmlab small{font-size:11px}
#bpmsrc{font-size:9.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#9fd0ff}#bpmsrc.man{color:#ffb86b}
#evslot{flex:1;min-width:0;height:30px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:800;letter-spacing:.08em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;border:1px solid #2a2e3c;color:#667;font-size:13px;font-weight:600;letter-spacing:0}
#evslot.drop{background:#e8110a;color:#fff;border-color:#e8110a;font-size:24px;font-weight:800;letter-spacing:.1em;animation:bl .3s infinite alternate}
#evslot.alert{background:#c0392b;color:#fff;border-color:#c0392b;font-size:19px;font-weight:800;letter-spacing:.06em;animation:bl .5s infinite alternate}
#evslot.build{background:#e8710a;color:#fff;border-color:#e8710a;font-size:20px;font-weight:800;letter-spacing:.06em}
#evslot.gap{background:#000;color:#fff;border:2px solid #e8710a;font-size:20px;font-weight:800;letter-spacing:.06em}
#evslot.frz{background:#1e90c8;color:#fff;border-color:#1e90c8;font-size:20px;font-weight:800}
#evslot.calm{color:#8ab4d8;border-color:#3a4a60}
#evslot.blk{background:#000;color:#e8710a;border:2px solid #e8710a;font-size:20px;font-weight:800;letter-spacing:.06em}
#evslot.sun{background:#f2d400;color:#222;border-color:#f2d400;font-size:20px;font-weight:800;letter-spacing:.06em}
#evslot.fogs{background:radial-gradient(ellipse at 30% 40%,rgba(230,234,240,.6),transparent 60%),linear-gradient(180deg,#7d858e,#555c63);color:#fff;border-color:#8a929b;font-size:20px;font-weight:800;letter-spacing:.06em}
#row2{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;height:20px;line-height:20px;font-size:13px;color:#aab;margin:4px 0 2px;white-space:nowrap}
#r2l{grid-column:1;min-width:0;overflow:hidden;text-overflow:ellipsis}#lvm{grid-column:2;justify-self:end}   /* links Betriebsart, Mitte Warnungen, rechts Pegel */
#lvm{flex:none;display:none;align-items:center;gap:5px;cursor:pointer}#lvm .lvb{position:relative;width:110px;height:9px;border-radius:3px;background:#2a2c3d;overflow:hidden}
#lvm .lvb i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:#3ddc84}#lvm .lvb b{position:absolute;top:0;bottom:0;width:2px;background:#fff}
#lvm.dead .lvb{background:none;border:1px dashed #556}#lvm.dead .lvb i,#lvm.dead .lvb b{display:none}#lvm.clip .lvb{background:#ff5a5a}#lvm.clip .lvb i{display:none}
#lvm small{font-size:10.5px;color:#9fd0ff;font-weight:600}
@media(max-width:400px){#lvm .lvb{width:60px}}
#dimrow{flex:1 1 330px;display:flex;align-items:center;gap:10px;height:32px;margin:0;padding-left:14px;border-left:1px solid #2f3346}   /* neben den Blitzen; zu schmal: eigene Zeile */
#dimlab{flex:none;font-size:13px;font-weight:700;color:#8ab4d8;letter-spacing:.04em;text-transform:uppercase}#dimlab b{color:#eee;margin-left:4px;font-variant-numeric:tabular-nums}
#dimrow input[type=range]{flex:1 1 auto;min-width:60px;margin:0}
#glbtn{flex:none;margin-left:auto;min-height:30px;padding:3px 12px;font-size:13px;color:#9fd0ff;background:#2a2c3d;border:1px solid #3a4560;border-radius:8px}#glbtn.on{border-color:#9fd0ff}#glbtn small{color:#ffb86b;font-weight:700;margin-left:4px}
#glpop{background:#1c1f2c;border-radius:10px;padding:8px 12px 10px;margin:2px 0 6px}#glbody{display:grid;grid-template-columns:1fr 1fr;gap:4px 18px}
#glbody .glit{display:flex;align-items:center;gap:8px;font-size:12.5px;color:#aab}#glbody .glit span{flex:0 0 84px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#glbody .glit input{flex:1;min-width:0;margin:0}
#glbody .glit b{flex:0 0 34px;text-align:right;color:#eee;font-variant-numeric:tabular-nums}#glbody .glit b.mod{color:#ffb86b}#glbody .glreset{grid-column:1/-1;justify-self:start;margin-top:4px;min-height:30px;padding:3px 12px;font-size:12px}
@media(max-width:520px){#glbody{grid-template-columns:1fr}#dimrow{gap:8px;padding-left:0;border-left:0}#glbtn{padding:3px 8px}#glbtn .glw{display:none}}
.bz{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.bzseg{display:flex;gap:5px}.bzseg button{min-height:32px;min-width:42px;padding:2px 8px;font-size:14px}.bzseg button.on{background:#d9822b;color:#fff;border-color:#d9822b}.bzseg button.cap{opacity:.45}
#bhz{color:#889;font-size:12px}
#row2 .modeb{color:#eee}#row2 .srcb{display:inline-block;vertical-align:baseline;font-size:9.5px;line-height:13px;font-weight:700;letter-spacing:.04em;color:#7ec8ff;background:#1e3550;border-radius:4px;padding:0 4px;margin-left:5px}
#mxline{display:flex;align-items:center;gap:8px;height:20px;line-height:20px;white-space:nowrap;margin:2px 0 6px;font-size:13px;color:#bbc}
#warnrow{display:flex;align-items:center;gap:6px;height:24px;margin-top:6px;padding-top:6px;border-top:1px solid #2c2f42;overflow-x:auto;white-space:nowrap;scrollbar-width:none}#warnrow::-webkit-scrollbar{display:none}   /* feste Hoehe: bei vielen Warnungen wischen, nichts springt */
#warnrow .wc{flex:none;font-size:12px;line-height:20px;padding:0 8px;border-radius:10px;font-weight:600;text-decoration:none;background:#3a2226;color:#ff8a7a;border:1px solid #6a3036}#warnrow .wc.o{background:#3a2e1c;color:#ffb86b;border-color:#6a5230}#warnrow .wc.i{background:#1e2c3c;color:#7ec8ff;border-color:#2f4a66}#warnrow .wc.pwr,#warnrow .wc.o,#warnrow .wc.i{cursor:pointer}#warnrow .wok{color:#889;font-size:12px}
#mxline .dot{flex:none;margin-right:0}
#lyricrow{display:flex;align-items:center;gap:8px;height:24px;margin:-2px 0 6px}   /* fester Platz: Wellenform und Knoepfe bleiben stehen, auch ohne Text */
#lyricpop{position:fixed;inset:0;z-index:60;background:#000a;display:flex;align-items:center;justify-content:center;padding:12px}
#lyricwin{background:#1d2030;border:1px solid #3a3e55;border-radius:10px;padding:10px;width:min(560px,100%);max-height:80vh;display:flex;flex-direction:column;gap:8px}
#lyrichead{display:flex;align-items:center;gap:8px}#lyricname{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#9fd0ff;font-size:13px}
#lyricx{flex:none;width:auto;min-height:0;padding:2px 10px;font-size:15px}
#pcover{flex:none;width:24px;height:24px;object-fit:cover;border-radius:4px}#pfav{flex:none;display:inline-flex;align-items:center}#pfav .favh{--fs:20px}   /* Cover des Liedes aus Mixxx (Musik-Datenbank) */
#lyricline{flex:1;min-width:0;font-size:15px;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#pquick{flex:none;min-height:0;padding:2px 10px;font-size:12px;width:auto;background:#2a6f3a;border:1px solid #3fbf6f;color:#eaffea}#pquick.run{background:#3a3320;border-color:#ffb86b;color:#ffb86b}#pquick.err{background:#3a2020;border-color:#ff6b6b;color:#ff9b9b}
#lyricbtn,#lyricre{flex:none;min-height:0;padding:2px 10px;font-size:12px;width:auto}#lyricline.msg{font-size:12px;font-weight:400;color:#889}
#lyricbox{flex:1 1 auto;min-height:120px;overflow:auto;background:#12131d;border-radius:8px;padding:6px 8px;font-size:14px;line-height:1.5;color:#aab}
#lyricbox div{padding:1px 4px;border-radius:4px}#lyricbox div.on{color:#fff;background:#2e4a78;font-weight:600}#lyricbox.tap div{cursor:pointer}#lyricbox .hint{color:#889;font-size:12px;margin-bottom:4px}
#mxline .mxl{flex:none;width:auto;white-space:nowrap;margin-right:6px}#mxline .mxl i{font-style:normal;font-size:11px;color:#889;margin-left:4px}#mxline .mxl i.fol{color:#2ecc40;font-weight:700}
#mxline .mxn{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
#mxline .mxe{display:inline-block;font-size:9.5px;line-height:13px;font-weight:800;border-radius:4px;padding:0 4px;margin-right:6px;vertical-align:baseline;color:#fff;background:#555a70}
#gsed .gsl{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:4px 14px;margin-top:6px}#gsed .gsr{display:flex;align-items:center;gap:8px;padding:3px 6px;border-radius:6px}#gsed .gsr.mod{box-shadow:inset 0 0 0 2px #e8710a}#gsed .gsn{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#gsed .gsn small{color:#889}#gsed select{max-width:150px}
#ebgrid button.nosnd{opacity:.45}
#mxline .mxg{color:#99a;font-size:11.5px;margin-left:8px}   /* Energiestufe von blau (ruhig) bis rot, Genre grau */
#mxline .mxs{flex:none;width:auto;min-width:152px;text-align:right;font-variant-numeric:tabular-nums;font-size:12.5px}
#mxline .mxtot{color:#99a;font-size:11.5px;font-weight:400;font-variant-numeric:tabular-nums;margin-right:5px}
#mxbar{display:block;width:100%;height:16px;margin:-3px 0 7px;border-radius:4px;background:#1f2130}#mxbar.ph{background:none}
.dot.info{background:#3a9ad9;box-shadow:0 0 6px #3a9ad9aa}
@media(max-width:400px){#mxline .mxs{min-width:136px;font-size:11.5px}#mxline .mxtot{font-size:10.5px;margin-right:3px}}
#toast{position:fixed;left:50%;transform:translateX(-50%);bottom:18px;max-width:92%;background:#222a3a;color:#fc6;padding:10px 16px;border-radius:10px;opacity:0;transition:opacity .25s;pointer-events:none;z-index:50;font-size:14px;box-shadow:0 4px 18px #000a}
#syssum .dot{margin-right:8px}
body.nohints [data-tx$="_hint"],body.nohints .scnote,body.nohints .hint{display:none!important}
details.sec{margin-top:16px}details.sec>summary{font-size:17px;font-weight:700;color:#8ad;letter-spacing:.3px}.secbody{padding:4px 8px 10px}
.secgrp{margin:22px 4px 6px;font-size:13px;color:#889;font-weight:700;text-transform:uppercase;letter-spacing:.06em}.secgrp+.seclink{margin-top:0}.seclink{display:block;margin-top:8px;padding:12px 14px;border-radius:10px;background:#1c1f2c;color:#8ad;font-size:17px;font-weight:700;text-decoration:none}
#apcsec{display:none}body.vapc #apcsec{display:block}body.vapc>*:not(#apcsec):not(#toast):not(script){display:none!important}
.apchead{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px}.apchead .seg{margin-left:auto}#apcconn{font-size:13px}
#apcboard{display:grid;grid-template-columns:minmax(0,1fr) 54px;gap:8px;max-width:780px;background:#25262c;border-radius:14px;padding:12px;margin-top:8px}
#apcpads{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:5px}#apcright{display:grid;grid-template-rows:repeat(8,1fr);gap:5px}
#apcbottom{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:5px}#apcshift{align-self:start}
.apad{position:relative;aspect-ratio:1.45;border-radius:5px;background:#3a3c46;font-size:10.5px;line-height:1.15;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:2px;overflow:hidden;text-shadow:0 1px 2px rgba(0,0,0,.7)}
.apad i{font-style:normal;font-size:9px;opacity:.85}.apad.free{background:#2c2d33;color:#667;text-shadow:none}.apad.pulse{animation:apcp 1s ease-in-out infinite alternate}
@keyframes apcp{from{filter:brightness(.7)}to{filter:brightness(1.25)}}
.abtn,#apcshift{border-radius:3px;background:#34363f;color:#ccd;font-size:10px;display:flex;align-items:center;justify-content:center;text-align:center;min-height:26px;padding:2px;line-height:1.1}
.abtn.on{background:#2e9e4a;color:#fff}.abtn.free{color:#667}
.flash{outline:3px solid #fff;outline-offset:-2px;filter:brightness(1.6)}
#apcfaders{grid-column:1/-1;display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:5px;margin-top:6px}
.afd{display:flex;flex-direction:column;align-items:center;font-size:10px;color:#ccd;gap:3px}.afd .tr{position:relative;width:12px;height:80px;border-radius:4px;background:#34363f;overflow:hidden}
.afd .tr b{position:absolute;left:0;right:0;bottom:0;background:#8fb3ff}.afd.mst .tr b{background:#ffb86b}.afd small{color:#889}
#lumisec{display:none}body.vlumi #lumisec{display:block}body.vlumi>*:not(#lumisec):not(#toast):not(script){display:none!important}
#lumiboard{max-width:900px;margin-top:8px;background:#0c0c0e;border-radius:16px;padding:0 3px 3px;box-shadow:0 8px 24px rgba(0,0,0,.45)}
#lumitop{display:flex;align-items:center;gap:14px;height:52px;padding:0 16px;color:#8a8a90}
#lumitop .pw{width:24px;height:24px;border-radius:50%;background:#1d1d21;border:1px solid #333;display:flex;align-items:center;justify-content:center}#lumitop .pw b{width:6px;height:6px;border-radius:50%;background:#333}#lumitop .pw b.ok{background:#3fdc6a}
#lumitop .oct{display:flex;align-items:center;background:#1d1d21;border:1px solid #333;border-radius:14px;height:28px}#lumitop .oct button{background:none;border:0;color:#ddd;font:inherit;font-size:17px;width:36px;height:28px;padding:0;cursor:pointer}#lumitop .oct button:disabled{color:#444;cursor:default}
#lumiwin{font-size:12px;color:#aab;flex:1}#lumitop .logo{font-weight:700;font-size:21px;letter-spacing:1.5px;color:#55555b}
#lumikeys{position:relative;display:flex;gap:2px;height:clamp(250px,40vw,350px);background:#000;border-radius:0 0 13px 13px;overflow:hidden}
.lumw{position:relative;flex:1 1 0;min-width:0;border-radius:0 0 7px 7px;background:#26272c;overflow:hidden}
.lumw.on{background:linear-gradient(var(--k),color-mix(in srgb,var(--k) 72%,#000))}
.lumt{position:absolute;left:0;right:0;display:flex;align-items:center;justify-content:center;writing-mode:vertical-rl;transform:rotate(180deg);color:#fff;font-size:12px;font-weight:600;line-height:1.05;text-align:center;text-shadow:0 1px 2px rgba(0,0,0,.7);overflow:hidden}
.lumw .lumt{top:59%;bottom:18px}.lumw.dk .lumt,.lumb.dk .lumt{color:#111;text-shadow:none}
.lumn{position:absolute;left:0;right:0;bottom:3px;text-align:center;font-size:9px;color:rgba(255,255,255,.6)}.lumw.dk .lumn{color:rgba(0,0,0,.6)}
.lumb{position:absolute;top:0;height:57%;width:4.9%;transform:translateX(-50%);background:#08080a;border-radius:0 0 7px 7px;padding:0 3px 8px;z-index:2}
.lumb i{position:relative;display:block;height:100%;font-style:normal;background:#26272c;border-radius:0 0 4px 4px;overflow:hidden}.lumb.on i{background:linear-gradient(var(--k),color-mix(in srgb,var(--k) 72%,#000))}
.lumb .lumt{top:3px;bottom:3px;font-size:11px}
#lumikeys.edit .lumw,#lumikeys.edit .lumb{cursor:pointer}.lumsel{outline:3px solid #fff;outline-offset:-3px}#lumipick select{font:inherit;min-height:38px;margin-left:8px;max-width:100%}#apcboard.edit .apad,#apcboard.edit .abtn,#apcboard.edit .afd{cursor:pointer}#apcpick select{font:inherit;min-height:38px;margin-left:8px;max-width:100%}#lumileg{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px;font-size:12px;color:#aab}#lumileg span{display:inline-flex;align-items:center;gap:5px}#lumileg b{width:12px;height:12px;border-radius:3px}
@media(max-width:520px){.lumt{font-size:9.5px}.lumb{padding:0 1px 5px}.lumb .lumt{font-size:8px}.lumw .lumt{bottom:14px}.lumn{font-size:7px}#lumitop{padding:0 10px;gap:8px}#lumitop .logo{font-size:16px}}
@media(max-width:520px){.apad{font-size:8px}.apad i{display:none}.abtn,#apcshift{font-size:8px}#apcboard{grid-template-columns:minmax(0,1fr) 40px;padding:8px}}
#setsec{display:none}body.vset #setsec{display:block}
body.vset>*:not(#setsec):not(#toast):not(script){display:none!important}
#fxsec{display:none}body.vfx #fxsec{display:block}
body.vfx>*:not(#fxsec):not(#toast):not(script){display:none!important}
</style></head><body>
<div id="hdr">
 <div id="row1"><span id="beat" onclick="tempoToggle(event)"></span><span id="bpmtxt" onclick="tempoToggle(event)" title="Tempo"><b id="bpmnum">--</b><span id="bpmlab"><span id="bpmsrc"></span><small>BPM</small></span></span>
  <div id="evslot" class="idle"><span id="evtext" data-tx="connecting">Verbinde ...</span></div><a id="hlbtn" href="/health" title="Zustand / Health"><svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor"><path d="M7.5 13.5S1 9.6 1 5.2C1 3 2.7 1.5 4.6 1.5c1.2 0 2.3.6 2.9 1.6.6-1 1.7-1.6 2.9-1.6C12.3 1.5 14 3 14 5.2c0 4.4-6.5 8.3-6.5 8.3z"/></svg></a><a id="djbtn" href="/musik/autodj" onclick="openAutoDJ(event)" title="Auto-DJ (eigenes Fenster)"><svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7.5" cy="7.5" r="6"/><circle cx="7.5" cy="7.5" r="1.6"/><path d="M4.2 5.3a4 4 0 0 1 2.1-1.6" stroke-linecap="round"/></svg></a><a id="dbbtn" href="/musik" title="Musik-Datenbank / Music library"><svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5"><ellipse cx="7.5" cy="3.5" rx="5.5" ry="2"/><path d="M2 3.5v8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-8M2 7.5c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2"/></svg></a><a id="rmbtn" href="/raum" title="Raumplan / Room plan"><svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1.5" y="2.5" width="12" height="10" rx="1"/><path d="M8.5 2.5v4.5h5M5 12.5V9.5"/></svg></a><a id="smbtn" href="/shows" title="Showmanager"><svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor"><path d="M1 3h13v2H1zM1 7h8v2H1zM1 11h11v2H1z"/><path d="M5 1.5h1.4v12H5z" opacity=".55"/></svg></a><a id="statbtn" href="/stats" title="Statistik / Statistics"><svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor"><rect x="1" y="8" width="3" height="6" rx="0.6"/><rect x="6" y="4" width="3" height="10" rx="0.6"/><rect x="11" y="1" width="3" height="13" rx="0.6"/></svg></a><a id="setbtn" href="/settings" title="Einstellungen / Settings"><svg width="17" height="17" viewBox="0 0 15 15" fill="currentColor" fill-rule="evenodd"><path d="M12.77 6.32 L14.44 6.59 L14.44 8.41 L12.77 8.68 L12.49 9.57 L12.06 10.39 L13.05 11.77 L11.77 13.05 L10.39 12.06 L9.57 12.49 L8.68 12.77 L8.41 14.44 L6.59 14.44 L6.32 12.77 L5.43 12.49 L4.61 12.06 L3.23 13.05 L1.95 11.77 L2.94 10.39 L2.51 9.57 L2.23 8.68 L0.56 8.41 L0.56 6.59 L2.23 6.32 L2.51 5.43 L2.94 4.61 L1.95 3.23 L3.23 1.95 L4.61 2.94 L5.43 2.51 L6.32 2.23 L6.59 0.56 L8.41 0.56 L8.68 2.23 L9.57 2.51 L10.39 2.94 L11.77 1.95 L13.05 3.23 L12.06 4.61 L12.49 5.43Z M7.5 5.2a2.3 2.3 0 1 0 0.001 0Z"/></svg></a><a id="helpbtn" href="/help" title="Handbuch / Manual">?</a><button id="powerbtn" onclick="powerOff()" title="Pi herunterfahren / Shut down Pi">⏻</button></div>
 <div id="tpop" style="display:none"><div class="tph"><b data-tx="tp_title">Tempo</b><span id="tpdet"></span></div>
  <div class="tpnow"><b id="tpval">--</b><small id="tpman"></small></div>
  <div class="tpbtns"><button onclick="bpmMul(0.5)">÷ 2</button><button onclick="bpmAdd(-1)">−1</button><button id="bpm_auto" data-tx="auto_btn" onclick="c({bpm:'auto'})">Auto</button><button onclick="bpmAdd(1)">+1</button><button onclick="bpmMul(2)">× 2</button></div>
  <button id="tptap" onpointerdown="tapTempo(event)" data-tx="tap_btn">TAP im Takt</button>
  <small data-tx="tempo_hint">Wirkt auf Szenen und WOW!, nicht auf AUTO. Außerhalb tippen schließt.</small></div>
 <div class="pbox" id="stbox"><div id="row2"><span id="r2l" data-tx="connecting">Verbinde ...</span><span id="lvm" onclick="openAudio()" title="Audio-Eingang"><span class="lvb"><i id="lvr"></i><b id="lvp"></b></span><small id="lvs"></small></span></div>
 <div id="mxline"><span class="mxl" style="color:#889">Mixxx</span><span class="mxn"></span><span class="mxs"></span></div>
 <div id="lyricrow"><img id="pcover" alt="" style="display:none"><span id="pfav" style="display:none"></span><div id="lyricline"></div><button id="lyricbtn" onclick="lyricToggle()" style="visibility:hidden"></button><button id="pquick" onclick="quickNow()" style="display:none"></button></div>
 <div id="lyricpop" style="display:none" onclick="if(event.target===this)lyricToggle()"><div id="lyricwin"><div id="lyrichead"><b id="lyricname"></b><button id="lyricre" onclick="lyricAgain()"></button><button id="lyricx" onclick="lyricToggle()" aria-label="Schließen">×</button></div><div id="lyricbox"></div></div></div>
 <canvas id="mxbar"></canvas><div id="warnrow"></div></div>
 <div id="fognote" style="display:none"><span id="fogtxt"></span><button id="fogok" data-tx="ok" onclick="c({fog_ack:S.fog_note||'on'})">OK</button></div>
</div>
<div id="toast"></div>
<div id="pwdlg" style="display:none" onclick="if(event.target===this)pwClose()"><div id="pwcard"><div data-tx="pw_q" id="pwtxt"></div><div id="pwdev"></div><div class="pwb"><button onclick="pwClose()" data-tx="pw_cancel">Abbrechen</button><button class="pwgo" onclick="pwGo()" data-tx="pw_go">Herunterfahren</button></div></div></div>
<div class="pbox"><div class="ctlrow">
<button class="big auto" id="b_auto" data-tx="auto" onclick="c({auto:'toggle'})">AUTO</button>
<button class="big bigfx halo" id="b_blitz" style="touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none"
 onpointerdown="holdStart('blitz',event)" onpointerup="holdStop('blitz')" onpointercancel="holdStop('blitz')" onlostpointercapture="holdStop('blitz')" oncontextmenu="return false">STROBE</button>
<button class="big bigfx halo" id="b_build" style="touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none"
 onpointerdown="wowStart(event)" onpointerup="wowStop()" onpointercancel="wowStop()" onlostpointercapture="wowStop()" oncontextmenu="return false">WOW!</button>
<button class="big sun" id="b_sun" data-tx="sun" style="touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none"
 onpointerdown="holdStart('allbright',event)" onpointerup="holdStop('allbright')" onpointercancel="holdStop('allbright')" onlostpointercapture="holdStop('allbright')" oncontextmenu="return false">BLINDER</button>
<button class="big bigfx" id="b_freeze" data-tx="freeze" style="touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none"
 onpointerdown="holdStart('freeze',event)" onpointerup="holdStop('freeze')" onpointercancel="holdStop('freeze')" onlostpointercapture="holdStop('freeze')" oncontextmenu="return false">FREEZE</button>
<button class="big bigfx" id="b_black" data-tx="black" style="touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none"
 onpointerdown="holdStart('blackout',event)" onpointerup="holdStop('blackout')" onpointercancel="holdStop('blackout')" onlostpointercapture="holdStop('blackout')" oncontextmenu="return false">BLACK<br>OUT</button>
<button class="big bigfx" id="b_fog" style="touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none"
 onpointerdown="fogDown(event)" onpointerup="holdStop('fog')" onpointercancel="holdStop('fog')" onlostpointercapture="holdStop('fog')" oncontextmenu="return false">SMOKE</button>
</div>
<div class="blitzrow">
<div class="bz"><span class="bzl"><span data-tx="bz_label">Flashes/s</span></span><div id="blitzhz" class="bzseg"></div><small id="bhz"></small></div>
<div id="dimrow"><span id="dimlab"><span data-tx="dim">General Dimmer</span> <b id="mv">100 %</b></span><input type="range" id="master" min="0" max="100" value="100" oninput="mdisp(this.value)" onchange="c({master:this.value/100})"><button id="glbtn" onclick="glToggle()"><span data-tx="gl_btn">Gruppen</span> <span id="glarr">▾</span> <small id="glmod"></small></button></div></div>
<div id="glpop" style="display:none"><div id="glbody"></div></div>
<div id="spst" class="lk"><div><h2 data-tx="h_speed">Speed</h2><div class="grid" id="speed"></div></div>
<div><h2 data-tx="h_style">Style</h2><div class="grid" id="style"></div></div></div></div>
<div class="pbox lk"><h2 data-tx="h_color">Color</h2><div class="grid" id="color"></div>
<small data-tx="color_hint" style="color:#889;display:block;margin-top:6px"></small>
<h2 data-tx="h_mix">Light Mix</h2><div class="grid" id="mix"></div><div class="fine" id="fine_mx"></div></div>
<div class="pbox lk"><h2 data-tx="h_move">Movement</h2><div class="grid" id="move"></div><div class="fine" id="fine_mv"></div>
<div class="schead"><h2 data-tx="h_aim" style="margin:0">Target for all movements</h2><button class="sedit" id="aim_edit" data-tx="edit" onclick="AIMEDIT=!AIMEDIT;AIMSIG='';draw()">✎ Edit</button></div>
<div class="grid" id="aim"></div><div id="aimed"></div>
<div id="aimset" style="display:none"><h2><span data-tx="aim_title">Position einstellen:</span> <span id="aimname"></span></h2>
<div><span data-tx="aim_vu">Moving Head links ↔ rechts</span> <span id="v_u"></span></div><input type="range" id="s_u" min="0" max="100" oninput="aimsend()">
<div><span data-tx="aim_vv">Moving Head oben ↔ unten</span> <span id="v_v"></span></div><input type="range" id="s_v" min="0" max="100" oninput="aimsend()">
<div><span data-tx="aim_bar">Spider wählen:</span> <span id="barsel"></span></div>
<div><span data-tx="aim_t1">Spider Tilt 1</span> <span id="v_t1"></span></div><input type="range" id="s_t1" min="10" max="220" oninput="aimsend()">
<div><span data-tx="aim_t2">Spider Tilt 2</span> <span id="v_t2"></span></div><input type="range" id="s_t2" min="10" max="220" oninput="aimsend()">
<div class="grid" style="margin-top:8px"><button class="big auto" onclick="c({aim_save:true})" data-tx="save">Speichern</button></div></div>
<h2 data-tx="h_beam">Beam</h2><div class="grid" id="beam"></div></div>
<div class="pbox lk" id="pagesbox"><div id="pages"></div></div>
<div class="pbox lk"><h2 data-tx="h_eb">Effektband</h2><div class="grid" id="ebgrid"></div>
<small data-tx="eb_hint" style="color:#889;display:block;margin-top:6px"></small></div>
<div id="setsec"><div class="s2lnav" data-back="/" data-cur="settings" data-title="h_setpage">Einstellungen</div>
<details id="genbox" class="sg sec"><summary data-tx="m_gen">Einstellungen allgemein</summary><div class="secbody">
<details id="sysbox" class="sg"><summary id="syssum">Verbindungen</summary><div id="sysbody" style="padding:6px 12px 12px"><div id="mrootrow" style="margin-bottom:12px"><div style="font-size:13px;color:#aab;margin-bottom:4px"><span data-tx="sys_music">Musikordner am Musik-Rechner (zum Beispiel USB-Stick)</span> <small style="color:#889" data-tx="sys_music_hint">(für Vorhören und „+ Show“ in der Musik-Datenbank; die Mixxx-Brücke holt ihn sich alle 30 s)</small></div><div style="display:flex;gap:6px;flex-wrap:wrap"><input id="mroot" placeholder="Pfad zum Musikordner, z. B. /Volumes/Stick/musik" style="flex:1 1 220px;min-width:160px;background:#10121a;border:1px solid #2c2f42;border-radius:6px;padding:6px 8px;color:#e8eaf2;font:inherit;font-size:14px"><button id="mrootsave" data-tx="save" onclick="saveMusicRoot()">Speichern</button><button id="meject" data-tx="sys_eject" onclick="ejectStick()" title="Den Musik-Stick am Musik-Rechner auswerfen: der Light-Butler hält seine Arbeit am Stick an, dann wirft der Musik-Rechner ihn aus. Wieder angesteckt, geht alles von selbst weiter.">⏏ Stick auswerfen</button></div><div id="mrootst" style="font-size:12px;color:#889;margin-top:4px"></div><div id="mejectst" style="font-size:12px;color:#ffd38a;margin-top:4px"></div></div><div id="mexclrow" style="margin-bottom:12px"><div style="font-size:13px;color:#aab;margin-bottom:4px"><span data-tx="sys_excl">Ausgeschlossene Ordner</span> <small style="color:#889" data-tx="sys_excl_hint">(je Zeile ein Ordner im Musikordner, etwa APRES SKI: der Light-Butler liest ihn nicht ein und ändert nichts darin; Mixxx sieht ihn trotzdem)</small></div><textarea id="mexcl" rows="4" placeholder="APRES SKI" spellcheck="false" style="width:100%;box-sizing:border-box;background:#10121a;border:1px solid #2c2f42;border-radius:6px;padding:6px 8px;color:#e8eaf2;font:inherit;font-size:14px"></textarea><div style="margin-top:4px"><button id="mexclsave" data-tx="save" onclick="saveMusicExcl()">Speichern</button></div><div id="mexclst" style="font-size:12px;color:#889;margin-top:4px"></div></div><div id="mnasrow" style="margin-bottom:12px"><div style="font-size:13px;color:#aab;margin-bottom:4px"><span data-tx="sys_nas">NAS (für „Spiegeln“)</span> <small style="color:#889">(Name oder IP, MAC-Adresse für „NAS wecken“, Uhrzeit, zu der sie abschaltet; leer = schaltet nicht ab)</small></div><div style="display:flex;gap:6px;flex-wrap:wrap"><input id="nashost" placeholder="Name oder IP" style="flex:1 1 160px;min-width:120px;background:#10121a;border:1px solid #2c2f42;border-radius:6px;padding:6px 8px;color:#e8eaf2;font:inherit;font-size:14px"><input id="nasmac" placeholder="MAC aa:bb:cc:dd:ee:ff" style="flex:1 1 160px;min-width:120px;background:#10121a;border:1px solid #2c2f42;border-radius:6px;padding:6px 8px;color:#e8eaf2;font:inherit;font-size:14px"><input id="nasoff" type="time" style="background:#10121a;border:1px solid #2c2f42;border-radius:6px;padding:6px 8px;color:#e8eaf2;font:inherit;font-size:14px"><button id="nassave" data-tx="save" onclick="saveNas()">Speichern</button></div><div id="nasst" style="font-size:12px;color:#889;margin-top:4px"></div></div><div id="olarow" style="margin-bottom:10px"><a id="dmxmon" href="/dmx" style="float:right;font-size:13px;color:#9fd0ff;text-decoration:none"><span data-tx="sys_dmxmon">DMX-Monitor</span> →</a><div style="font-size:13px;color:#aab;margin-bottom:4px"><span data-tx="sys_ola">DMX-Ausgabe</span> <small style="color:#889" data-tx="sys_ola_hint">(aus = andere Art-Net-Sender können ihn nutzen)</small></div><div class="seg"><button id="ola_off" data-tx="off" onclick="c({set:{ola_out:0,ola_have:1}})">Aus</button><button id="ola_on" data-tx="on" onclick="c({set:{ola_out:1,ola_have:1}})">An</button><button id="ola_none" data-tx="not_have" title="Diese Anlage hat das nicht: keine Warnung, keine Prüfung, ob es erreichbar ist" onclick="c({set:{ola_out:0,ola_have:0}})">Nicht vorhanden</button></div>
<div style="font-size:13px;color:#aab;margin:10px 0 4px"><span data-tx="sys_via">DMX-Weg</span> <small style="color:#889" data-tx="sys_via_hint">(USB = FTDI-Adapter direkt an diesem Licht-Rechner, ohne Art-Net-Gateway)</small> <span id="usbst"></span></div><div class="seg"><button id="via_ola" data-tx="via_ola" onclick="c({set:{dmx_via:0}})">Art-Net-Gateway</button><button id="via_usb" data-tx="via_usb" onclick="c({set:{dmx_via:1}})">USB-Adapter</button></div>
<div style="font-size:13px;color:#aab;margin:10px 0 4px"><span data-tx="sys_artin">Art-Net-Eingang</span> <small style="color:#889" data-tx="sys_artin_hint">(für ein anderes Lichtprogramm; Laser, Nebel und ohne Erlaubnis Strobe bleiben gesperrt)</small> <span id="artinst"></span></div><div class="seg"><button id="artin_off" data-tx="off" onclick="c({set:{artnet_in:0}})">Aus</button><button id="artin_on" data-tx="on" onclick="c({set:{artnet_in:1}})">An</button></div>
<div style="font-size:13px;color:#aab;margin:10px 0 4px"><span data-tx="sys_wled">Ausgabe an die WLED-Lichter</span> <small style="color:#889" data-tx="sys_wled_hint">(Effektband, Theke, Couchtisch; aus = sie sind frei für die WLED-App)</small></div><div class="seg"><button id="wled_off" data-tx="off" onclick="c({set:{wled_out:0,wled_have:1}})">Aus</button><button id="wled_on" data-tx="on" onclick="c({set:{wled_out:1,wled_have:1}})">An</button><button id="wled_none" data-tx="not_have" title="Diese Anlage hat das nicht: keine Warnung, keine Prüfung, ob es erreichbar ist" onclick="c({set:{wled_out:0,wled_have:0}})">Nicht vorhanden</button></div>
<div id="nanorow" style="display:none"><div style="font-size:13px;color:#aab;margin:10px 0 4px"><span data-tx="sys_nano">Ausgabe an die Nanoleaf-Panels</span> <small style="color:#889" data-tx="sys_nano_hint">(aus = Panels gehen zurück auf ihren Effekt und sind frei für die Nanoleaf-App)</small></div><div class="seg"><button id="nano_off" data-tx="off" onclick="c({set:{nano_out:0,nano_have:1}})">Aus</button><button id="nano_on" data-tx="on" onclick="c({set:{nano_out:1,nano_have:1}})">An</button><button id="nano_none" data-tx="not_have" title="Diese Anlage hat das nicht: keine Warnung, keine Prüfung, ob es erreichbar ist" onclick="c({set:{nano_out:0,nano_have:0}})">Nicht vorhanden</button></div></div>
<div style="font-size:13px;color:#aab;margin:10px 0 4px"><span data-tx="sys_link">Ableton Link</span> <small style="color:#889" data-tx="sys_link_hint">(Tempo per LAN und WLAN an Link-Geräte, bei Stille 20 BPM)</small> <span id="linkst" style="color:#9fd0ff"></span></div><div class="seg"><button id="link_off" data-tx="off" onclick="c({set:{link_on:0}})">Aus</button><button id="link_on" data-tx="on" onclick="c({set:{link_on:1}})">An</button></div></div><div id="reach"></div><div id="net"></div></div></details>
<details id="homebox" class="sg"><summary data-tx="m_home">Haus</summary><div id="homebody" style="padding:6px 12px 12px"></div></details>
<details id="bkbox" class="sg"><summary data-tx="m_backup">Sicherung</summary><div id="bkbody" style="padding:6px 12px 12px">Lade ...</div></details>
<details id="midibox" class="sg"><summary data-tx="m_midi">MIDI-Controller (APC mini mk2)</summary><a href="/apc" style="display:block;margin:8px 12px 0;color:#9fd0ff;text-decoration:none;font-weight:700"><span data-tx="apc_page">Belegung als Grafik</span> →</a><div id="midibody" style="padding:6px 12px 12px">Lade ...</div></details>
<details id="audiobox" class="sg"><summary data-tx="m_audio">Audio-Eingang</summary><div id="audiobody" style="padding:6px 12px 12px">Lade ...</div></details>
<div id="genset"></div></div></details>
<details id="autobox" class="sg sec"><summary data-tx="h_settings">Einstellungen (Auto-Erkennung)</summary><div class="secbody">
<div id="setbar"><button onclick="if(confirm(TXT.set_all_q[LANG==='de'?0:1]))c({reset:'all'}).then(loadSet)" data-tx="set_all">Alle auf Standard</button><span id="setnote" data-tx="set_note">Änderungen wirken sofort und bleiben gespeichert.</span></div>
<div id="setlist"></div></div></details>
<div class="secgrp" data-tx="nav_devices">Geräte</div><a id="fxlink" class="seclink" href="/fixtures"><span data-tx="h_fixtures">Fixtures</span> →</a><a class="seclink" href="/raum"><span data-tx="h_room">Raumplan</span> →</a><a class="seclink" href="/apc"><span data-tx="apc_title">APC mini · Belegung</span> →</a><a class="seclink" href="/lumi"><span data-tx="lumi_title">ROLI Lumi · Belegung</span> →</a><div class="secgrp" data-tx="nav_tech">Technik</div><a class="seclink" href="/dmx"><span data-tx="sys_dmxmon">DMX-Monitor</span> →</a><a class="seclink" href="/dmx-debug"><span data-tx="h_dmxdebug">DMX-Debugger</span> →</a><div class="secgrp" data-tx="nav_soft">Software für andere Rechner</div><a class="seclink" href="/software"><span data-tx="h_software">Systemschema und Downloads</span> →</a><div style="font-size:12px;color:#889;margin:0 2px 6px" data-tx="sw_hint">Welcher Teil gehört auf welchen Rechner? Im Schema das Symbol antippen, dann kommt das passende Paket.</div><a class="seclink" href="/download/light-butler-mac.zip" download><span data-tx="dl_mac">Mac: Mixxx-Brücke und Helfer (ZIP)</span> ⬇</a><a class="seclink" href="/download/light-butler-windows.zip" download><span data-tx="dl_win">Windows: Pegelkurven (ZIP)</span> ⬇</a><a class="seclink" href="/download/light-butler-windows-voll.zip" download><span data-tx="dl_win_full">Windows: ganzer Light-Butler (ZIP)</span> ⬇</a><a class="seclink" href="/download/light-butler-windows-exe.zip" download><span data-tx="dl_win_exe">Windows: Light-Butler.exe ohne Python (ZIP)</span> ⬇</a><a class="seclink" href="/download/light-butler-mac-voll.zip" download><span data-tx="dl_mac_full">Mac: ganzer Light-Butler (ZIP)</span> ⬇</a><a class="seclink" href="/download/light-butler-pi.zip" download><span data-tx="dl_pi">Pi: frische Installation (ZIP)</span> ⬇</a><a class="seclink" href="/download/light-butler-pi-ersatz.zip" download><span data-tx="dl_pi_own">Pi: Ersatzgerät mit meinen Geräten (ZIP)</span> ⬇</a><a class="seclink" href="/download/backup" download><span data-tx="dl_backup">Jüngste Sicherung des Light-Butler (ZIP)</span> ⬇</a><div style="font-size:12px;color:#889;margin:4px 2px 0" data-tx="dl_hint">Für einen neuen Rechner: entpacken, LIESMICH.txt lesen, das Installationsskript richtet alles samt Python-Paketen ein.</div><div style="font-size:12px;color:#889;margin:4px 2px 0" data-tx="dl_pi_hint">Neuer Raspberry Pi (Pi OS 64 Bit): ZIP auf den Pi kopieren, entpacken, bash install_pi.sh. Ohne persönliche Daten; das Ersatzgerät enthält zusätzlich deine Geräte mit ihren Adressen. Startet mit allen Ausgaben aus.</div><div style="font-size:12px;color:#889;margin:4px 2px 0" data-tx="dl_backup_hint">Die Sicherung entsteht jede Nacht um 04:30 am Light-Butler. Zum Aufheben auf einem anderen Gerät, ohne Nanoleaf-Token und Claude-Schlüssel.</div><div class="secgrp" data-tx="h_about">Über Light-Butler</div><a class="seclink" href="/about"><span data-tx="h_about">Über Light-Butler</span> →</a></div>
<div id="hlsec" class="stsec"><div class="s2lnav" data-back="/" data-cur="health" data-title="hl_title">Zustand des Light-Butler</div>
<div id="hlhead"></div><div id="hlbody" class="stgrid"></div></div>
<div id="statsec" class="stsec"><div class="s2lnav" data-back="/" data-cur="stats" data-title="stat_title">Statistik</div>
<small id="statage" style="color:#889"></small><div id="statbody" class="stgrid"></div></div>
<div id="presec" class="stsec"><div class="s2lnav" data-back="/musik/pflege" data-cur="musik" data-title="h_pre">Vorab-Läufe</div>
<div id="lybulk" class="stc" style="margin:8px 0"></div><div id="mkbulk" class="stc" style="margin:8px 0"></div><div id="cvbulk" class="stc" style="margin:8px 0"></div><div id="arbulk" class="stc" style="margin:8px 0"></div><div id="prstick" class="stc" style="margin:8px 0"></div><div id="stemstat" class="stc" style="margin:8px 0"></div><div id="stbulk" class="stc" style="margin:8px 0"></div></div>
<div id="apcsec"><div class="s2lnav" data-back="/settings" data-cur="settings" data-title="apc_title">APC mini · Belegung</div>
<div class="apchead"><span id="apcconn"></span>
<button class="sedit" id="apcedit" data-tx="lumi_edit">Umbelegen</button><div class="seg" id="apcpg"><button data-p="pads1" class="on" data-tx="apc_main">Hauptseite</button><button data-p="pads2" data-tx="apc_colors">Farbseite</button></div></div>
<div id="apcboard"><div id="apcpads"></div><div id="apcright"></div><div id="apcbottom"></div><div id="apcshift">SHIFT</div><div id="apcfaders"></div></div>
<div id="apcform" style="display:none;margin-top:10px;max-width:780px;font-size:14px;color:#ccd"><div id="apcpick"></div><button class="sedit" id="apcreset" style="margin-top:8px" data-tx="lumi_reset">Standard wiederherstellen</button></div>
<small data-tx="apc_hint" style="color:#889;display:block;margin-top:8px">Pads in ihrer LED-Farbe wie am Gerät, gedrückte Tasten blitzen kurz auf. Ändern mit dem Knopf Umbelegen.</small></div>
<div id="lumisec"><div class="s2lnav" data-back="/settings" data-cur="settings" data-title="lumi_title">ROLI Lumi · Belegung</div>
<div class="apchead"><span id="lumiconn"></span><button class="sedit" id="lumiedit" style="margin-left:auto" data-tx="lumi_edit">Umbelegen</button><a class="sedit" href="/lumi/LightButler.littlefoot" download="LightButler.littlefoot" data-tx="lumi_dl">&#11015; Lumi-Programm</a></div>
<div id="lumiboard"><div id="lumitop"><span class="pw"><b id="lumidot"></b></span><span class="oct"><button id="lumidn" aria-label="Oktave runter">&lsaquo;</button><button id="lumiup" aria-label="Oktave hoch">&rsaquo;</button></span><span id="lumiwin"></span><span class="logo">LUMI</span></div><div id="lumikeys"></div></div>
<div id="lumiform" style="display:none;margin-top:10px;max-width:900px;font-size:14px;color:#ccd"><div id="lumipick"></div><div id="lumistale" data-tx="lumi_stale" style="display:none;margin-top:8px;color:#ffb86b">Die Tasten am Lumi leuchten noch in den alten Farben: Lumi-Programm neu herunterladen und im ROLI Dashboard auf den Lumi ziehen.</div><button class="sedit" id="lumireset" style="margin-top:8px" data-tx="lumi_reset">Standard wiederherstellen</button></div>
<div id="lumileg"></div>
<small data-tx="lumi_hint" style="color:#889;display:block;margin-top:8px">Die Pfeile zeigen die übrigen Seiten, wie die Pfeile am Lumi. Gedrückte Tasten blitzen auf. Die Tasten am Gerät zeigen diese Farben, wenn das Lumi-Programm geladen ist (Knopf oben, Datei im ROLI Dashboard auf den Lumi ziehen). Ändern mit dem Knopf Umbelegen.</small></div>
<div id="fxsec"><div class="s2lnav" data-back="/settings" data-cur="settings" data-title="h_fixtures">Fixtures</div>
<h2 style="display:flex;align-items:center;gap:8px;margin-top:0"><span style="flex:1"></span><a class="sedit" id="fx_exp" href="/fixtures.yaml" download="fixtures.yaml" data-tx="fx_export">&#11015; Export (YAML)</a><button class="sedit" id="fx_edit">&#9998; Bearbeiten</button></h2>
<div id="fxbar"></div>
<div id="fixlist"></div>
<div id="fxremoved"></div></div>
<script>
const MIXP=__MIXP__, MOVES=__MOVES__, COLORS=__COLORS__, SPEEDS=__SPEEDS__, AIMS=__AIMS__, STYB=__STYB__, STYHUE=__STYHUE__;
const ECOL=['#2f4f8f','#33609f','#2f7a9a','#2f8a80','#2f8a5a','#6f9933','#339933','#997733','#993333','#b02a5a'];   // Energiestufe E1-E10: blau ruhig bis rot, 7-9 wie die Trackfarben in Mixxx
let LANG='',TXT=__TEXTS__,TXREV=-1,HL=null;
function tr(k){const t=TXT[k];return esc(t?t[LANG==='de'?0:1]:k).replace(/[|]/g,'<br>')}
function setLang(l,force){l=l==='de'?'de':'en';const hb=document.getElementById('helpbtn');if(hb)hb.href='/help?lang='+l;if(l===LANG&&!force)return;LANG=l;if(window.S2LNAV)S2LNAV.set(l,TXT);document.documentElement.lang=l;
 document.querySelectorAll('[data-tx]').forEach(e=>e.innerHTML=tr(e.dataset.tx));
 document.querySelectorAll('[data-tk]').forEach(b=>b.innerHTML=tr(b.dataset.tk));if(HL)drawHealth();
 const bc=document.body.classList;if(bc.contains('vpre'))loadPre();if(bc.contains('vstat'))loadStats()}
async function loadTexts(){try{const r=await fetch('/api/texts');const D=await r.json();TXT=D.texts;TXREV=D.rev;setLang(LANG,true);if(TXED)renderTxEd(D.table)}catch(e){}}
let S={};
async function c(d){const r=await fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
 const j=await r.json();if(!r.ok){alert(j.error||'Fehler');return}S=j;draw()}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
let FIXOPEN=new Set(),FXEDIT=false,FXCAT=null,FXL=[],FXADD=false,FXTYPES=false,TF=null;
const GRPL={bars:'Spider',wash:'Wash',bar:'Barlicht',fx:'Effekt (Eyes, Derby)',uv:'UV-Leiste',spot:'Moving Head',ambient:'Ambiente (WLED)',locked:'gesperrt (nie angesteuert)',nano:'Nanoleaf'};
async function loadCat(){try{const r=await fetch('/api/fxcat');FXCAT=await r.json()}catch(e){}}
async function loadFix(){
 try{const r=await fetch('/api/fixtures');FXL=await r.json();await loadCat();renderFix()}catch(e){}}
function gopts(list,cur){return list.map(g=>'<option value="'+esc(g)+'"'+(g===cur?' selected':'')+'>'+esc(GRPL[g]||g)+'</option>').join('')}
function fxRestart(){
 if(!confirm('Jetzt neu starten? Das Licht ist dabei etwa 5 Sekunden aus.'))return;
 c({restart:true});
 const ov=document.createElement('div');ov.style.cssText='position:fixed;inset:0;background:#000d;color:#fff;display:flex;align-items:center;justify-content:center;font-size:20px;z-index:99';ov.textContent='Neustart ...';document.body.appendChild(ov);
 let down=false,n=0;const iv=setInterval(async()=>{n++;try{const r=await fetch('/api/state',{cache:'no-store'});if(r.ok&&(down||n>12)){clearInterval(iv);location.reload()}}catch(e){down=true}if(n>40){clearInterval(iv);location.reload()}},1000)}
function renderFxBars(){
 const bar=document.getElementById('fxbar');let h='';
 if(S.fx_pending)h+='<div class="fxpend"><span style="flex:1">Gespeicherte Änderungen (Adresse, Gruppe, neue oder entfernte Fixtures) gelten erst nach einem Neustart.</span><button class="ok" id="fx_rs">Jetzt neu starten</button></div>';
 if(FXCAT&&FXCAT.warning)h+='<div style="color:#ff6b5a;font-size:13px;margin:6px 0">'+esc(FXCAT.warning)+'</div>';
 if(FXEDIT){
  h+='<div class="fxtools"><button id="fx_add" class="'+(FXADD?'on':'')+'">+ Fixture</button><button id="fx_types" class="'+(FXTYPES?'on':'')+'">Gerätetypen</button>'+(FXCAT&&FXCAT.has_changes?'<button id="fx_reset" class="del">Änderungen verwerfen</button>':'')+'</div>';
  h+='<small style="color:#889;display:block;margin-bottom:6px">Fixture antippen zum Aufklappen. Name und Nummer wirken sofort, Adresse, Gruppe, Ziel, neue und entfernte Fixtures nach dem Neustart. Kanalbeschreibungen sind direkt im Kanal-Raster editierbar. Der Export enthält alle Änderungen (Kommentare der Original-Datei fehlen darin).</small>';
  if(FXADD)h+='<div id="fxaddbox"></div>';
  if(FXTYPES)h+='<div id="fxtypebox"></div>';
 }
 bar.innerHTML=h;
 const rs=document.getElementById('fx_rs');if(rs)rs.onclick=fxRestart;
 if(FXEDIT){
  document.getElementById('fx_add').onclick=()=>{FXADD=!FXADD;if(FXADD)FXTYPES=false;renderFxBars()};
  document.getElementById('fx_types').onclick=()=>{FXTYPES=!FXTYPES;if(FXTYPES){FXADD=false;TF=null}renderFxBars()};
  const rb=document.getElementById('fx_reset');if(rb)rb.onclick=()=>{if(confirm('Alle Änderungen aus dem Panel verwerfen? Danach gilt wieder nur die Datei fixtures.yaml (nach dem Neustart).'))c({fx_reset:true}).then(loadFix)};
  if(FXADD)buildAdd();if(FXTYPES)buildTypes()}}
function buildAdd(){
 const box=document.getElementById('fxaddbox');if(!FXCAT||!FXCAT.editable){box.textContent='Nicht verfügbar';return}
 const types=FXCAT.types.filter(t=>t.groups[0]!=='nano');
 box.className='fxa2';
 box.innerHTML='<div class="row"><label class="wide" style="grid-column:1/3">Gerätetyp<select id="na_type">'+types.map(t=>'<option value="'+esc(t.name)+'">'+esc(t.name)+' ('+t.channels+' Kanäle'+(t.custom?', eigener Typ':'')+')</option>').join('')+'</select></label>'+
  '<label>Name<input id="na_label" placeholder="z. B. Wash 12"></label><label>Nummer<input id="na_nr" type="number" min="0" max="999" value="'+FXCAT.next_nr+'"></label>'+
  '<label>DMX-Adresse<input id="na_addr" type="number" min="1" max="512"></label><label>Gruppe<select id="na_group"></select></label>'+
  '<label class="wide" style="grid-column:1/3">Ziel-IP (nur für Geräte mit eigener Adresse, leer = Art-Net-Gateway)<input id="na_target" placeholder="192.168.1.30"></label></div>'+
  '<div class="ebtn"><button class="ok" id="na_ok">Hinzufügen</button><button id="na_cancel">Abbrechen</button></div>';
 const upd=()=>{const t=types.find(x=>x.name===document.getElementById('na_type').value);document.getElementById('na_addr').value=FXCAT.addresses[t.name]||1;document.getElementById('na_group').innerHTML=gopts(t.groups,t.groups[0])};
 document.getElementById('na_type').onchange=upd;upd();
 document.getElementById('na_cancel').onclick=()=>{FXADD=false;renderFxBars()};
 document.getElementById('na_ok').onclick=()=>{
  c({fx_save:{new:true,type:document.getElementById('na_type').value,label:document.getElementById('na_label').value,nr:+document.getElementById('na_nr').value,address:+document.getElementById('na_addr').value,group:document.getElementById('na_group').value,target:document.getElementById('na_target').value.trim()}}).then(()=>{FXADD=false;loadFix()})}}
function typeRows(){return TF.channels.map((ch,i)=>'<tr><td>'+(i+1)+'</td><td><input list="roles" data-i="'+i+'" data-f="param" value="'+esc(ch.param)+'" style="min-width:70px"></td><td><input data-i="'+i+'" data-f="desc" value="'+esc(ch.desc||'')+'"></td><td><input data-i="'+i+'" data-f="default" type="number" min="0" max="255" value="'+esc(ch.default||0)+'" style="width:66px"></td><td><input data-i="'+i+'" data-f="max" type="number" min="0" max="255" value="'+esc(ch.max===undefined?255:ch.max)+'" style="width:66px"></td></tr>').join('')}
function fromType(t){const inv={};Object.entries(t.map).forEach(([p,i])=>inv[i]=p);const ch=[];for(let i=1;i<=t.channels;i++){const p=inv[i]||'';ch.push({param:p,desc:(t.desc||{})[p]||'',default:(t.defaults||{})[p]||0,max:(t.limits&&t.limits[p])?t.limits[p][1]:255})}return ch}
function buildTypes(){
 const box=document.getElementById('fxtypebox');box.className='fxt';
 const custom=FXCAT.types.filter(t=>t.custom);
 let h='<datalist id="roles"><option value="dimmer"><option value="r"><option value="g"><option value="b"><option value="w"><option value="uv"><option value="strobe"></datalist>';
 h+='<div style="font-size:13px;color:#aab;margin-bottom:6px">Eigene Gerätetypen ('+custom.length+')</div>';
 h+=custom.map(t=>'<div class="fxrm" style="margin:4px 0"><div><span><b>'+esc(t.name)+'</b> ('+t.channels+' Kanäle)</span><button data-edit="'+esc(t.name)+'">Bearbeiten</button><button class="del" data-del="'+esc(t.name)+'">Löschen</button></div></div>').join('')||'<small style="color:#889">Noch keine eigenen Typen.</small>';
 h+='<div class="ebtn"><button id="tf_new">+ Neuer Typ</button><select id="tf_copy" style="flex:1 1 40%"><option value="">Kopie von ...</option>'+FXCAT.types.map(t=>'<option value="'+esc(t.name)+'">'+esc(t.name)+'</option>').join('')+'</select></div>';
 if(TF){
  h+='<div style="margin-top:10px"><div class="row"><label style="grid-column:1/3">Typname (Kleinbuchstaben, Ziffern, _)<input id="tf_name" value="'+esc(TF.name)+'" '+(TF.locked?'readonly':'')+' placeholder="mein_par_8ch"></label></div>'+
   '<div style="overflow-x:auto"><table><tr><th>Kanal</th><th>Parameter</th><th>Beschreibung</th><th>Std.</th><th>Max.</th></tr>'+typeRows()+'</table></div>'+
   '<small style="color:#889;display:block;margin:6px 0">Parameter: dimmer, r, g, b, w, uv und strobe nutzt das Licht selbst. Für Farbgeräte werden r, g und b zusammen gebraucht. Andere Kanäle (mode, speed ...) bleiben beim Standardwert, Max. begrenzt sie zur Sicherheit (zum Beispiel Mode-Kanal auf 10).</small>'+
   '<div class="ebtn"><button id="tf_addch">+ Kanal</button><button id="tf_delch">Letzten Kanal entfernen</button><button class="ok" id="tf_save">Typ speichern</button></div></div>';
 }
 box.innerHTML=h;
 box.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>{const t=custom.find(x=>x.name===b.dataset.edit);TF={name:t.name,channels:fromType(t),locked:true};buildTypes()});
 box.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{if(confirm('Typ '+b.dataset.del+' löschen?'))c({type_delete:b.dataset.del}).then(loadFix)});
 document.getElementById('tf_new').onclick=()=>{TF={name:'',channels:[{param:'dimmer',desc:'Master-Dimmer',default:255,max:255},{param:'r',desc:'Rot',default:0,max:255},{param:'g',desc:'Grün',default:0,max:255},{param:'b',desc:'Blau',default:0,max:255}],locked:false};buildTypes()};
 document.getElementById('tf_copy').onchange=e=>{const t=FXCAT.types.find(x=>x.name===e.target.value);if(t){TF={name:'',channels:fromType(t),locked:false};buildTypes()}};
 if(TF){
  const sync=()=>{box.querySelectorAll('input[data-f]').forEach(i=>{const ch=TF.channels[+i.dataset.i];const f=i.dataset.f;ch[f]=(f==='default'||f==='max')?(i.value===''?'':+i.value):i.value});TF.name=document.getElementById('tf_name').value};
  document.getElementById('tf_addch').onclick=()=>{sync();TF.channels.push({param:'',desc:'',default:0,max:255});buildTypes()};
  document.getElementById('tf_delch').onclick=()=>{sync();if(TF.channels.length>1)TF.channels.pop();buildTypes()};
  document.getElementById('tf_save').onclick=()=>{sync();c({type_save:{name:TF.name,channels:TF.channels.map(x=>({param:x.param,desc:x.desc,default:x.default,max:x.max}))}}).then(()=>{TF=null;loadFix()})}}}
function editForm(f){
 return '<div class="fxf"><label class="wide">Name<input data-k="label" value="'+esc(f.label)+'"></label><label>Nummer<input data-k="nr" type="number" min="0" max="999" value="'+esc(f.nr)+'"></label><label>DMX-Adresse<input data-k="address" type="number" min="1" max="512" value="'+f.address+'"></label>'+
  '<label>Gruppe<select data-k="group">'+gopts(f.allowed.includes(f.group)?f.allowed:f.allowed.concat([f.group]),f.group)+'</select></label><label>Ziel-IP<input data-k="target" placeholder="leer = Art-Net-Gateway" value="'+esc(f.own_target||'')+'"></label>'+
  '<div class="ebtn"><button class="ok" data-a="save">Speichern</button><button class="del" data-a="del">Entfernen</button></div><small>Typ '+esc(f.type)+' ('+f.n+' Kanäle). Name und Nummer gelten sofort, der Rest nach dem Neustart.</small></div>'}
function nanoForm(f){return '<div class="fxf"><label class="wide">IP-Adresse der Nanoleaf-Panels<input data-k="nano_host" placeholder="'+esc(f.nano_file_host)+'" value="'+esc(f.nano_user_host||f.nano_host)+'"></label>'+
  '<div class="ebtn"><button class="ok" data-a="nanosave">Speichern</button></div><small>Aus nanoleaf.json: '+esc(f.nano_file_host)+'. Leer = diese Adresse. Gilt nach dem Neustart.</small>'+
  '<label class="wide">API-Key (Token) <span style="color:#9fd0ff">'+(f.nano_token_changed?'neu gespeichert, gilt nach dem Neustart':f.nano_token_set?'hinterlegt':'fehlt')+'</span><input data-k="nano_token" type="password" autocomplete="off" placeholder="neuen Token eingeben"></label>'+
  '<div class="ebtn"><button class="ok" data-a="nanotoken">Token speichern</button></div><small>Der Token wird nie angezeigt. Vor dem Speichern wird er am Nanoleaf geprüft. Gilt nach dem Neustart.</small></div>'}
function renderFix(){
 const fe=document.getElementById('fx_edit');fe.dataset.tx=FXEDIT?'done':'edit';fe.innerHTML=tr(fe.dataset.tx);
 renderFxBars();
 const box=document.getElementById('fixlist');box.innerHTML='';
 FXL.forEach(f=>{
  const nano=f.type==='nanoleaf_panel',ed=FXEDIT&&!nano;
  const d=document.createElement('div');d.className='fx';
  const h=document.createElement('div');h.className='fxh';
  h.innerHTML='<span class="fxn">#'+esc(f.nr)+'</span><span class="fxl">'+esc(f.label)+(f.locked?' <small style="color:#c8a050">(gesperrt)</small>':'')+(f.user_added?' <small style="color:#7ec8ff">neu/geändert</small>':'')+'</span><span class="fxa">ab DMX '+f.address+(f.nano_host||f.own_target?' · '+esc(f.nano_host||f.own_target):'')+'</span>';
  const b=document.createElement('div');b.className='fxb';b.style.display=FIXOPEN.has(f.name)?'block':'none';
  let t=(FXEDIT&&nano?nanoForm(f):'')+(f.hw_strobe?'<div style="padding:6px 4px"><button class="sbtest" data-n="'+esc(f.name)+'">Einzel-Strobe testen (3 s)</button>'+(f.blitz_ok?'':' <small style="color:#889">nicht im allgemeinen Strobe (dunkel)</small>')+'</div>':'')+(ed?editForm(f):'');
  t+='<table><tr><th>Kanal</th><th>DMX</th><th>Beschreibung</th><th>Wert</th></tr>';
  f.channels.forEach(c2=>{
   const dcell=(ed&&c2.param)?'<textarea class="fxd" rows="'+Math.min(7,Math.max(1,Math.ceil(c2.desc.length/30)))+'" data-type="'+esc(f.type)+'" data-param="'+esc(c2.param)+'" title="Beschreibung (wirkt für alle Geräte dieses Typs)">'+esc(c2.desc)+'</textarea>'+(c2.note?'<small>'+esc(c2.note)+'</small>':''):esc(c2.desc)+(c2.note?'<br><small>'+esc(c2.note)+'</small>':'');
   t+='<tr><td>'+c2.ch+'</td><td>'+c2.dmx+'</td><td>'+(ed&&c2.param?'<small style="color:#889">'+esc(c2.param)+'</small><br>':'')+dcell+'</td><td class="val" id="v_'+f.name+'_'+c2.ch+'"><span class="vn">-</span><span class="bar"><i></i></span></td></tr>'});
  b.innerHTML=t+'</table>';
  b.querySelectorAll('.sbtest').forEach(x=>x.onclick=()=>c({solo_test:x.dataset.n}));
  const ns=b.querySelector('[data-a="nanosave"]');if(ns)ns.onclick=()=>c({nano_host:b.querySelector('[data-k="nano_host"]').value.trim()}).then(loadFix);
  const nt=b.querySelector('[data-a="nanotoken"]');if(nt)nt.onclick=()=>{const i=b.querySelector('[data-k="nano_token"]');const v=i.value.trim();i.value='';if(v)c({nano_token:v}).then(loadFix)};
  if(ed){
   b.querySelectorAll('.fxd').forEach(i=>i.onchange=()=>c({fx_desc:{type:i.dataset.type,param:i.dataset.param,text:i.value}}));
   b.querySelector('[data-a="save"]').onclick=()=>{const g=k=>b.querySelector('[data-k="'+k+'"]').value;
    c({fx_save:{name:f.name,label:g('label'),nr:+g('nr'),address:+g('address'),group:g('group'),target:g('target').trim()}}).then(loadFix)};
   b.querySelector('[data-a="del"]').onclick=()=>{if(confirm('Fixture '+f.label+' entfernen? Es verschwindet nach dem Neustart aus der Show (Wiederherstellen bleibt möglich).'))c({fx_delete:f.name}).then(loadFix)}}
  h.onclick=()=>{const o=b.style.display==='none';b.style.display=o?'block':'none';if(o)FIXOPEN.add(f.name);else FIXOPEN.delete(f.name);pollFix()};
  d.appendChild(h);d.appendChild(b);box.appendChild(d)});
 const rm=document.getElementById('fxremoved');
 rm.innerHTML=(FXEDIT&&FXCAT&&FXCAT.removed&&FXCAT.removed.length)?'<div class="fxrm"><div style="color:#aab;font-size:13px">Entfernte Fixtures (aus fixtures.yaml)</div>'+FXCAT.removed.map(x=>'<div><span>#'+esc(x.nr)+' '+esc(x.label)+' (DMX '+x.address+')</span><button data-rs="'+esc(x.name)+'">Wiederherstellen</button></div>').join('')+'</div>':'';
 rm.querySelectorAll('[data-rs]').forEach(b=>b.onclick=()=>c({fx_restore:b.dataset.rs}).then(loadFix))}
document.getElementById('fx_edit').onclick=()=>{FXEDIT=!FXEDIT;if(!FXEDIT){FXADD=false;FXTYPES=false;TF=null}loadFix()};
async function pollFix(){
 if(!FIXOPEN.size)return;
 try{const r=await fetch('/api/dmx?names='+encodeURIComponent([...FIXOPEN].join(',')));const V=await r.json();
 for(const [n,vals] of Object.entries(V)){vals.forEach((v,i)=>{const c=document.getElementById('v_'+n+'_'+(i+1));if(c){c.firstChild.textContent=v;c.lastChild.firstChild.style.width=(v/2.55)+'%'}})}}catch(e){}}
loadFix();setInterval(pollFix,500);
let SETOPEN=new Set();
function dec(step){const s=String(step);return s.indexOf('.')>=0?s.split('.')[1].length:0}
async function loadSet(){
 try{const r=await fetch('/api/settings');const L=await r.json();const box=document.getElementById('setlist');box.innerHTML='';
 const gen=document.getElementById('genset');if(gen)gen.innerHTML='';
 L.forEach(g=>{const d=document.createElement('details');d.className='sg';if(SETOPEN.has(g.group))d.open=true;
  d.addEventListener('toggle',()=>{if(d.open)SETOPEN.add(g.group);else SETOPEN.delete(g.group)});
  const sm=document.createElement('summary');const nm=g.items.filter(i=>i.mod).length;sm.innerHTML='<span data-tk="grp:'+esc(g.group)+'">'+tr('grp:'+g.group)+'</span>'+esc(nm?'  ('+nm+' geaendert)':'');d.appendChild(sm);
  g.items.forEach(it=>{
   const row=document.createElement('div');row.className='srow'+(it.mod?' mod':'');
   const dc=dec(it.step);
   if(it.unit.indexOf('switch:')===0){
    const lab=it.unit.slice(7).split('|');
    row.innerHTML='<div class="sname">'+esc(it.label)+'</div><div class="sdesc">'+esc(it.desc)+'</div><div class="seg">'+lab.map((l,i)=>'<button data-v="'+i+'"'+(Math.round(it.value)===i?' class="on"':'')+'>'+esc(l)+'</button>').join('')+'</div><div class="sdef">Standard: '+esc(lab[Math.round(it.default)])+'</div>';
    row.querySelectorAll('.seg button').forEach(bt=>bt.onclick=()=>{c({set:{[it.key]:+bt.dataset.v}}).then(()=>{row.querySelectorAll('.seg button').forEach(x=>x.classList.toggle('on',x===bt));row.classList.toggle('mod',+bt.dataset.v!==Math.round(it.default))})});
    row.querySelector('.sdef').insertAdjacentHTML('afterend','<button class="sres" title="Auf Standard" style="margin-top:4px">&#8634;</button>');
    row.querySelector('.sres').onclick=()=>{c({reset:it.key}).then(loadSet)};
    d.appendChild(row);return}
   row.innerHTML='<div class="sname">'+esc(it.label)+'</div><div class="sdesc">'+esc(it.desc)+'</div><div class="sctl"><input type="range" min="'+it.lo+'" max="'+it.hi+'" step="'+it.step+'" value="'+it.value+'"><input type="number" min="'+it.lo+'" max="'+it.hi+'" step="'+it.step+'" value="'+Number(it.value).toFixed(dc)+'"><span class="sunit">'+esc(it.unit)+'</span><button class="sres" title="Auf Standard">&#8634;</button></div><div class="sdef">Standard: '+Number(it.default).toFixed(dc)+' '+esc(it.unit)+' (Bereich '+it.lo+' bis '+it.hi+')</div>';
   const rg=row.querySelector('input[type=range]'),nu=row.querySelector('input[type=number]');
   const send=v=>{v=Math.max(it.lo,Math.min(it.hi,+v));rg.value=v;nu.value=v.toFixed(dc);row.classList.toggle('mod',Math.abs(v-it.default)>1e-9);c({set:{[it.key]:v}})};
   rg.oninput=()=>{nu.value=(+rg.value).toFixed(dc)};rg.onchange=()=>send(rg.value);nu.onchange=()=>send(nu.value);
   row.querySelector('.sres').onclick=()=>{c({reset:it.key}).then(loadSet)};
   d.appendChild(row)});
  if(g.group==='Weisse Blitze und Strobo'){const sr=document.createElement('div');sr.className='srow';
   sr.innerHTML='<div class="sname" data-tx="strobe_perm">'+tr('strobe_perm')+'</div><div class="sdesc" data-tx="strobe_perm_desc">'+tr('strobe_perm_desc')+'</div><button class="big" id="b_strobe" onclick="toggleStrobe()" style="min-height:50px;padding:6px 16px"></button>';
   d.insertBefore(sr,sm.nextSibling);drawStrobe()}
  if(g.group==='Panel'){const tb=document.createElement('div');tb.id='txed';tb.className='srow';d.appendChild(tb);TXED=true;loadTexts()}
  if(g.group==='Mixxx-Vorhersage'){const gb=document.createElement('div');gb.id='gsed';gb.className='srow';d.appendChild(gb);loadGenres()}
  (GEN_GROUPS.includes(g.group)&&gen?gen:box).appendChild(d)})}catch(e){}}
let TXED=false;
// Liedzeile im Hauptpanel: alles nur als Text gesetzt, nie als HTML
let lyricOpen=false,lyricKey=null;
let coverKey=null,QK=null,qBusy=false;
// Herz zum laufenden Lied (Favoriten, 14.11.2026; Einstellung fav_panel). Antippen setzt oder nimmt das Herz (SM.favToggle in core.js)
async function favNow(m){const b=document.getElementById('pfav');if(!b)return;b.style.display='none';b.innerHTML='';if(!m||!window.SM||!SM.favHtml)return;const k=coverKey;
 try{const r=await fetch('/api/sm/fav_now?t='+encodeURIComponent(m.title)+'&d='+Math.round(m.dur||0));const j=await r.json();if(k!==coverKey||!j.panel||!j.path)return;
  await SM.favLoad();if(k!==coverKey)return;b.innerHTML=SM.favHtml('song',j.path,{name:m.title});b.style.display=''}catch(e){}}
function drawQuick(){const b=document.getElementById('pquick');if(!b||qBusy)return;const de=LANG==='de',q=QK;
 const ok=!!(q&&!q.show&&q.stems&&q.song&&q.song.mp3&&q.music&&window.SM&&SM.quickShow);b.style.display=ok?'':'none';b.className='';
 if(ok){b.textContent=de?'⚡ Quick-Show':'⚡ Quick show';b.title=de?'Für dieses Lied gibt es noch keine Show: anlegen, vom Assistenten füllen lassen (offline, Standardwerte) und gleich zum laufenden Lied starten':'No show for this song yet: create it, let the assistant fill it (offline, defaults) and start it right away with the playing song'}}
async function quickCheck(m){QK=null;drawQuick();if(!m)return;const k=coverKey;
 try{const r=await fetch('/api/sm/quick_check?t='+encodeURIComponent(m.title)+'&d='+Math.round(m.dur||0));const j=await r.json();if(k===coverKey){QK=j;drawQuick()}}catch(e){}}
async function quickNow(){const b=document.getElementById('pquick'),q=QK,de=LANG==='de';if(qBusy||!q||!q.song)return;qBusy=true;b.className='run';
 try{const name=await SM.quickShow(q.song,q.music,t=>{b.textContent=t});await SM.cmd('mixxx_once',{});b.textContent=de?'✓ Show startet':'✓ Show starting';b.title=name;
  setTimeout(()=>{qBusy=false;const m=S.mx;quickCheck(m&&m.title?m:null)},8000)}
 catch(e){b.className='err';b.textContent=de?'✗ nochmal':'✗ retry';b.title=e.message;qBusy=false;b.onclick=()=>{b.onclick=quickNow;quickNow()}}}
function drawCover(){const im=document.getElementById('pcover');if(!im)return;const m=S.mx,on=!!(m&&m.connected&&m.deck!==null&&m.title),sh=S.sm_show||'';
 const k=sh?'show|'+sh:on?m.title+'|'+Math.round(m.dur||0):'';if(k===coverKey)return;coverKey=k;if(!qBusy)quickCheck(on&&!sh?m:null);favNow(on?m:null);
 if(sh){im.onload=()=>{im.style.display=''};im.onerror=()=>{im.style.display='none'};im.src='/api/sm/cover?show='+encodeURIComponent(sh);return}
 if(!on){im.style.display='none';im.removeAttribute('src');return}
 im.onload=()=>{im.style.display=''};im.onerror=()=>{im.style.display='none'};im.src='/api/sm/cover?t='+encodeURIComponent(m.title)+'&d='+Math.round(m.dur||0)}
function drawLyric(){const row=document.getElementById('lyricrow');if(!row)return;const l=document.getElementById('lyricline'),b=document.getElementById('lyricbtn'),re=document.getElementById('lyricre'),pop=document.getElementById('lyricpop'),box=document.getElementById('lyricbox'),t=S.lyric||'',m=t?'':(S.lyric_msg||''),can=!!(S.lyric_avail||S.lyric_again);
 if(l.dataset.t!==t+'|'+m){l.dataset.t=t+'|'+m;l.textContent=t?'♪ '+t:m;l.classList.toggle('msg',!t)}
 re.style.display=S.lyric_again?'':'none';re.textContent=LANG==='de'?'Text neu suchen':'Search again';
 b.style.visibility=can?'visible':'hidden';b.textContent='Text';
 if(!can)lyricOpen=false;
 pop.style.display=lyricOpen?'':'none';if(!lyricOpen)return;
 document.getElementById('lyricname').textContent=S.lyric_key||'';
 if(lyricKey!==(S.lyric_key||'')+'|'+(S.lyric_msg||''))lyricLoad();
 box.classList.toggle('tap',!!S.lyric_tap);
 box.querySelectorAll('[data-i]').forEach(e=>{const on=+e.dataset.i===S.lyric_i;if(e.classList.contains('on')!==on){e.classList.toggle('on',on);if(on)e.scrollIntoView({block:'nearest'})}})}
function lyricToggle(){lyricOpen=!lyricOpen;lyricKey=null;drawLyric()}
async function lyricAgain(){const q=prompt(LANG==='de'?'Wonach suchen? (Interpret - Titel, anpassen wenn der Text nicht passt)':'Search for what? (artist - title, change it if the text is wrong)',S.lyric_key||'');if(q===null)return;
 try{await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify({op:'lyric_refetch',query:q})});lyricKey=null}catch(e){}}
async function lyricLoad(){lyricKey=(S.lyric_key||'')+'|'+(S.lyric_msg||'');const box=document.getElementById('lyricbox');let d;try{d=await (await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify({op:'lyric_full'})})).json()}catch(e){return}
 box.textContent='';if(!(d.lines||[]).length&&!d.plain){const h=document.createElement('div');h.className='hint';h.textContent=LANG==='de'?'Zu diesem Lied gibt es noch keinen Text. Mit Text neu suchen kannst du es mit anderem Interpret oder Titel versuchen.':'No lyrics for this song yet. Use Text neu suchen to try another artist or title.';box.appendChild(h);return}if(S.lyric_tap){const h=document.createElement('div');h.className='hint';h.textContent=LANG==='de'?'Zeile antippen, die gerade gesungen wird: Der Light-Butler rechnet ab dort weiter.':'Tap the line being sung: the Light-Butler continues from there.';box.appendChild(h)}
 (d.lines||[]).forEach((x,i)=>{if(!x[1])return;const e=document.createElement('div');e.dataset.i=i;e.textContent=x[1];e.onclick=()=>{if(S.lyric_tap)fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify({op:'lyric_sync',i})})};box.appendChild(e)});
 if(!(d.lines||[]).length)String(d.plain||'').split(String.fromCharCode(10)).forEach(x=>{const e=document.createElement('div');e.textContent=x;box.appendChild(e)})}
async function loadStats(){try{const r=await fetch('/api/stats');drawStats(await r.json())}catch(e){}}
function loadPre(){loadLyBulk();loadMkBulk();loadCvBulk();loadArBulk();loadPrStick();loadStemStat();loadStemBulk()}
async function loadStemStat(){try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify({op:'stems_summary'})});drawStemStat(await r.json())}catch(e){}}
function drawStemStat(s){const b=document.getElementById('stemstat');if(!b||!s||s.mp3===undefined)return;const de=LANG==='de';
 b.innerHTML='<h3>'+(de?'Spur-Kurven':'Stem curves')+'</h3><p class="dim" style="margin:4px 0"></p><div style="height:6px;background:#2c2f42;border-radius:3px;overflow:hidden;margin:6px 0"><i style="display:block;height:100%;background:#3fbf6f;width:'+(s.mp3?Math.min(100,Math.round(s.done*100/s.mp3)):0)+'%"></i></div>';
 b.querySelector('p').textContent=s.done+(de?' von ':' of ')+s.mp3+(de?' MP3s der Shows zerlegt und ausgewertet (am Musik-Rechner).':' MP3s of the shows separated and analysed (on the music computer).')}
async function mkBulkCmd(o){try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify(o)});drawMkBulk(await r.json())}catch(e){}}
function loadMkBulk(){mkBulkCmd({op:'marks_bulk_status'})}
function drawMkBulk(s){const b=document.getElementById('mkbulk');if(!b||!s||s.total===undefined)return;const de=LANG==='de',nf=x=>Number(x||0).toLocaleString(de?'de-AT':'en-GB');
 const want=Math.max(0,s.total-(s.bad||0)),pc=want?Math.floor(s.done*1000/want)/10:0,left=Math.max(0,want-s.done-(s.missing||0));
 b.innerHTML='<h3>'+(de?'Cue-Punkte vorab holen':'Fetch cue points in advance')+'</h3><p class="dim" style="margin:4px 0"></p><div style="height:6px;background:#2c2f42;border-radius:3px;overflow:hidden;margin:6px 0"><i style="display:block;height:100%;background:#3fbf6f;width:'+Math.min(100,pc)+'%"></i></div><button></button>';
 b.querySelector('p').textContent=nf(s.done)+(de?' von ':' of ')+nf(want)+(de?' Liedern mit Cue-Punkten und Abschnitten am Light-Butler (':' songs with cue points and sections on the Light-Butler (')+pc.toLocaleString(de?'de-AT':'en-GB')+' %).'
  +(s.missing?(de?' Am Musik-Rechner noch nicht analysiert: ':' Not yet analysed on the music computer: ')+nf(s.missing)+'.':'')
  +(s.bad?(de?' Dazu ':' Plus ')+nf(s.bad)+(de?' nicht lesbare Dateien, die nie eine Analyse bekommen (Musik-Datenbank, Filter nicht lesbar).':' unreadable files that never get an analysis (music library, filter unreadable).'):'')
  +(s.running&&left?(de?' Noch etwa ':' About ')+Math.max(1,Math.ceil(left*0.9/60))+(de?' Minuten.':' minutes left.'):'')
  +(s.running&&!s.music?(de?' Wartet auf den Musik-Rechner (Mixxx-Brücke).':' Waiting for the music computer (Mixxx bridge).'):'')
  +(s.error?' '+s.error:'')+(s.current?' '+s.current:'')+(s.done_all&&!s.running?(de?' Erledigt.':' Done.'):'');
 const k=b.querySelector('button');if(s.done_all&&!s.running&&!s.missing){k.remove();return}k.textContent=s.running?(de?'Anhalten':'Stop'):(de?'Starten':'Start');k.onclick=()=>mkBulkCmd({op:'marks_bulk',on:!s.running})}
async function cvBulkCmd(o){try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify(o)});drawCvBulk(await r.json())}catch(e){}}
function loadCvBulk(){cvBulkCmd({op:'covers_bulk_status'})}
function drawCvBulk(s){const b=document.getElementById('cvbulk');if(!b||!s||s.total===undefined)return;const de=LANG==='de',nf=x=>Number(x||0).toLocaleString(de?'de-AT':'en-GB');
 const seen=s.done+(s.none||0),pc=s.total?Math.floor(seen*1000/s.total)/10:0,left=Math.max(0,s.total-seen);
 b.innerHTML='<h3>'+(de?'Cover vorab holen':'Fetch covers in advance')+'</h3><p class="dim" style="margin:4px 0"></p><div style="height:6px;background:#2c2f42;border-radius:3px;overflow:hidden;margin:6px 0"><i style="display:block;height:100%;background:#3fbf6f;width:'+Math.min(100,pc)+'%"></i></div><button></button>';
 b.querySelector('p').textContent=nf(seen)+(de?' von ':' of ')+nf(s.total)+(de?' Liedern angesehen (':' songs checked (')+pc.toLocaleString(de?'de-AT':'en-GB')+' %): '+nf(s.done)+(de?' mit Cover, ':' with cover, ')+nf(s.none||0)+(de?' ohne.':' without.')
  +(s.running&&left?(de?' Noch etwa ':' About ')+Math.max(1,Math.ceil(left*0.5/60))+(de?' Minuten.':' minutes left.'):'')
  +(s.running&&!s.music?(de?' Wartet auf den Musik-Rechner (Mixxx-Brücke).':' Waiting for the music computer (Mixxx bridge).'):'')
  +(s.error?' '+s.error:'')+(s.current?' '+s.current:'')+(s.done_all&&!s.running?(de?' Erledigt.':' Done.'):'');
 const k=b.querySelector('button');if(s.done_all&&!s.running){k.remove();return}k.textContent=s.running?(de?'Anhalten':'Stop'):(de?'Starten':'Start');k.onclick=()=>cvBulkCmd({op:'covers_bulk',on:!s.running})}
// Programme am Stick (14.11.2026): Pakete, Handbuecher und Sicherung kopiert der Helfer am Mac in Light-Butler-Programme
async function loadPrStick(){const b=document.getElementById('prstick');if(!b)return;let s={};try{s=await (await fetch('/api/sm/programs')).json()}catch(e){}
 const de=LANG==='de',when=s.t?new Date(s.t*1000).toLocaleString(de?'de-AT':'en-GB',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}):'';
 b.innerHTML='<h3>'+(de?'Programme am Musik-Stick':'Programs on the music stick')+'</h3><p class="dim" style="margin:4px 0"></p>';
 b.querySelector('p').textContent=!s.t?(de?'Noch nicht kopiert. Der Helfer am Musik-Rechner legt den Ordner Light-Butler-Programme neben dem Musikordner an, sobald Stick und Light-Butler erreichbar sind.':'Not copied yet. The helper on the music computer creates the folder Light-Butler-Programme next to the music folder once stick and Light-Butler are reachable.')
  :(de?'Stand ':'As of ')+when+(s.mb?' · '+s.mb.toLocaleString(de?'de-AT':'en-GB')+' MB':'')+' · '+(s.files||[]).length+(de?' Dateien':' files')+(s.backup?(de?' · Sicherung ':' · backup ')+s.backup:'')+(s.dir?' · '+s.dir:'')+(s.err?' · '+s.err:'')}
async function arBulkCmd(o){try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify(o)});drawArBulk(await r.json())}catch(e){}}
function loadArBulk(){arBulkCmd({op:'artists_bulk_status'})}
function drawArBulk(s){const b=document.getElementById('arbulk');if(!b||!s||s.total===undefined)return;const de=LANG==='de',nf=x=>Number(x||0).toLocaleString(de?'de-AT':'en-GB');
 const seen=s.done+(s.none||0),pc=s.total?Math.floor(seen*1000/s.total)/10:0,left=Math.max(0,s.total-seen);
 b.innerHTML='<h3>'+(de?'Interpreten-Bilder vorab holen':'Fetch artist pictures in advance')+'</h3><p class="dim" style="margin:4px 0"></p><div style="height:6px;background:#2c2f42;border-radius:3px;overflow:hidden;margin:6px 0"><i style="display:block;height:100%;background:#3fbf6f;width:'+Math.min(100,pc)+'%"></i></div><button></button> <a href="/musik/interpreten" class="dim">'+(de?'Interpreten ansehen':'Show artists')+'</a>';
 b.querySelector('p').textContent=nf(seen)+(de?' von ':' of ')+nf(s.total)+(de?' Interpreten gesucht (':' artists searched (')+pc.toLocaleString(de?'de-AT':'en-GB')+' %): '+nf(s.done)+(de?' mit Bild, ':' with picture, ')+nf(s.none||0)+(de?' ohne Treffer.':' not found.')
  +(s.running&&left?(de?' Noch etwa ':' About ')+Math.max(1,Math.ceil(left*4/60))+(de?' Minuten.':' minutes left.'):'')
  +(s.error?' '+s.error:'')+(s.current?' '+s.current:'')+(s.done_all&&!s.running?(de?' Erledigt.':' Done.'):'');
 const k=b.querySelector('button');if(s.done_all&&!s.running){k.remove();return}k.textContent=s.running?(de?'Anhalten':'Stop'):(de?'Starten':'Start');k.onclick=()=>arBulkCmd({op:'artists_bulk',on:!s.running})}
async function stBulkCmd(o){try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify(o)});drawStemBulk(await r.json())}catch(e){}}
function loadStemBulk(){stBulkCmd({op:'stems_bulk_status'})}
function drawStemBulk(s){const b=document.getElementById('stbulk');if(!b||!s||s.total===undefined)return;const de=LANG==='de',nf=x=>Number(x||0).toLocaleString(de?'de-AT':'en-GB');
 const w=(s.work||[]).map(x=>x.who+': '+x.title+' ('+x.since_s+' s)').join(' · ');
 const left=(s.total||0)-(s.done||0)-(s.fail||0);
 let st=s.on&&left<=0&&!(s.work||[]).length?(s.fail?(de?'Fertig bis auf '+nf(s.fail)+' mit Fehler (Liste unten). „Fehler neu versuchen“ gibt sie wieder frei; ohne Windows-PC rechnet sie dann der Helfer am Musik-Rechner (Light-Butler Helfer).':'Done except '+nf(s.fail)+' failed (list below). "Retry failed" releases them again; without the Windows PC the helper on the music computer computes them (Light-Butler helper).'):(de?'Fertig.':'Done.'))
  :s.on?(!s.music?(de?'Wartet: Der Light-Butler erreicht den Musik-Rechner gerade nicht (die MP3s kommen von dort).':'Waiting: the Light-Butler cannot reach the music computer right now (the MP3s come from there).')
  :!(s.workers||[]).length?(de?'Kein Rechner holt Arbeit: Am Windows-PC muss der Wächter laufen (Aufgabe „Light-Butler Pegelkurven“). Fehlen nur noch wenige (bis 50), rechnet sie der Helfer am Musik-Rechner (Light-Butler Helfer).':'No computer is fetching work: the watcher must run on the Windows PC (task "Light-Butler Pegelkurven"). If only a few (up to 50) are left, the helper on the music computer computes them (Light-Butler helper).')
  :(w?(de?'Rechnet: ':'Processing: ')+w:(de?'Rechner bereit: ':'Ready: ')+s.workers.join(', '))):(de?'Angehalten.':'Stopped.');
 if(s.on&&s.eta_h!=null&&s.total>s.done)st+=' '+(de?'Noch etwa ':'About ')+(s.eta_h<1?(de?'eine Stunde':'one hour'):Math.ceil(s.eta_h)+(de?' Stunden':' hours'))+(de?' (':' (')+s.avg_s+(de?' s je Lied).':' s per song).');
 b.innerHTML='<h3>'+(de?'Spur-Kurven vorab (Bibliothek)':'Stem curves in advance (library)')+'</h3><p class="dim" style="margin:4px 0"></p><div style="height:6px;background:#2c2f42;border-radius:3px;overflow:hidden;margin:6px 0"><i style="display:block;height:100%;background:#3fbf6f;width:'+(s.total?Math.min(100,Math.round(s.done*100/s.total)):0)+'%"></i></div><p class="dim" style="margin:4px 0"></p><button></button>'+(s.fail?' <button id="stretry"></button>':'')+((s.failed||[]).length?'<details style="margin-top:8px"><summary class="dim" style="cursor:pointer"></summary><ul id="stfails" style="margin:6px 0 0;padding-left:18px;font-size:13px"></ul></details>':'');
 const P=b.querySelectorAll('p');P[0].textContent=nf(s.done)+(de?' von ':' of ')+nf(s.total)+(de?' Liedern (30 s bis '+(s.max_min?s.max_min+' min':'beliebig lang')+') haben Kurven':' songs (30 s to '+(s.max_min?s.max_min+' min':'any length')+') have curves')+(s.fail?', '+nf(s.fail)+(de?' mit Fehler':' failed'):'')+(de?'. Ausgelassen: ':'. Skipped: ')+nf(s.long)+(de?' zu lang':' too long')+(s.other?', '+nf(s.other)+(de?' keine MP3 (MP4, WAV …)':' not MP3 (MP4, WAV …)'):'')+'.';
 P[1].textContent=st;
 const k=b.querySelector('button');k.textContent=s.on?(de?'Anhalten':'Stop'):(de?'Starten':'Start');k.onclick=()=>stBulkCmd({op:'stems_bulk',on:!s.on});if(s.on&&left<=0&&!(s.work||[]).length)k.hidden=true;
 const fl=document.getElementById('stfails');if(fl){b.querySelector('details summary').textContent=(de?'Lieder mit Fehler anzeigen (':'Show failed songs (')+s.failed.length+')';
  for(const f of s.failed){const li=document.createElement('li');li.textContent=f.title+': '+f.error;li.title=f.path;fl.appendChild(li)}}
 const rb=document.getElementById('stretry');if(rb){rb.textContent=de?'Fehler neu versuchen':'Retry failed';rb.title=de?'Lieder mit Fehler gleich wieder versuchen statt erst nach einem Tag':'Try failed songs again now instead of after a day';rb.onclick=()=>stBulkCmd({op:'stems_bulk_retry'})}}
async function lyBulkCmd(o){try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify(o)});drawLyBulk(await r.json())}catch(e){}}
function loadLyBulk(){lyBulkCmd({op:'lyrics_bulk_status'})}
function drawLyBulk(s){const b=document.getElementById('lybulk');if(!b||!s||s.error===undefined)return;const de=LANG==='de',nf=x=>Number(x||0).toLocaleString(de?'de-AT':'en-GB'),left=Math.max(0,(s.total||0)-(s.seen||0));
 const eta=s.running&&left?' '+(de?'Noch etwa ':'About ')+Math.ceil(left*3/3600)+(de?' Stunden.':' hours left.'):'';
 b.innerHTML='<h3>'+(de?'Liedtexte vorab holen':'Fetch lyrics in advance')+'</h3><p class="dim" style="margin:4px 0"></p><div style="height:6px;background:#2c2f42;border-radius:3px;overflow:hidden;margin:6px 0"><i style="display:block;height:100%;background:#3fbf6f;width:'+(s.total?Math.min(100,Math.round(s.seen*100/s.total)):0)+'%"></i></div><button></button>';
 const pc=s.total?Math.floor(s.seen*1000/s.total)/10:0;b.querySelector('p').textContent=nf(s.seen)+(de?' von ':' of ')+nf(s.total)+(de?' Liedern gesucht (':' songs searched (')+pc.toLocaleString(de?'de-AT':'en-GB')+' %), '+nf(s.found)+(de?' mit Liedtext.':' with lyrics.')+(s.done&&!s.running?(de?' Erledigt.':' Done.'):'')+eta+(s.error?' '+s.error:'')+(s.current?' '+s.current:'');
 const k=b.querySelector('button');if(s.done&&!s.running){k.remove();return}k.textContent=s.running?(de?'Anhalten':'Stop'):(de?'Starten':'Start');k.onclick=()=>lyBulkCmd({op:'lyrics_bulk',on:!s.running})}
function drawStats(D){const box=document.getElementById('statbody');if(!box)return;const L=D.lib,nf=x=>Number(x||0).toLocaleString(LANG==='de'?'de-AT':'en-GB');
 const pct=(a,n)=>n?Math.round(100*a/n):0,bar=(a,n,col)=>'<div class="pbar"><i style="width:'+pct(a,n)+'%'+(col?';background:'+col:'')+'"></i></div>';
 let h='';
 if(!L){h='<div class="stc">'+tr('stat_nolib')+'</div>';document.getElementById('statage').textContent=''}
 else{document.getElementById('statage').textContent=tr('stat_age').replace('#',D.age||0);
  h+='<div class="stc"><h3>'+tr('stat_lib')+'</h3><div class="big"><div><b>'+nf(L.n)+'</b><span>'+tr('stat_tracks')+'</span></div><div><b>'+nf(L.a)+'</b><span>'+tr('stat_done')+' ('+pct(L.a,L.n)+' %)</span></div><div><b>'+nf(L.h)+'</b><span>'+tr('stat_hours')+'</span></div><div><b>'+nf(L.cu)+'</b><span>'+tr('stat_cues')+'</span></div></div>'+bar(L.a,L.n)
   +(()=>{const B=L.bg;if(!B)return '<small style="color:#99a;display:block">'+tr('stat_bg')+': '+tr('stat_bg_off')+'</small>';
     const st=B.run?(B.pause?tr('stat_bg_pause'):tr('stat_bg_run')):tr('stat_bg_end'),gone=Math.min(B.gone||0,B.fail||0),bad=(B.fail||0)-gone,k=[B.done,B.todo,bad];let i=0;
     return '<small style="color:#9fd0ff;display:block;margin:4px 0">'+tr('stat_bg')+': '+st+' · '+tr('stat_bg_line').replace(/#/g,()=>nf(k[i++]))+(bad?' <a href="/musik?f=nichtlesbar" style="color:#9fd0ff">'+(LANG==='de'?'anzeigen →':'show →')+'</a>':'')+(gone?'<br><span style="color:#99a">'+esc(tr('stat_bg_gone').replace('#',nf(gone)))+'</span>':'')+'</small>'+bar(B.done,B.todo,'#2f80e0')})()
   +'<small style="color:#99a">'+tr('stat_files')+': '+Object.entries(L.ft||{}).map(([k,v])=>esc(k)+' '+nf(v)).join(' · ')+'</small></div>';
  h+='<div class="stc"><h3>'+tr('stat_styles')+'</h3>';
  const sty=Object.entries(D.styles||{}).concat([['',D.nostyle||[0,0]]]);
  sty.forEach(([k,v])=>{const hu=STYHUE[k],bg=hu?'linear-gradient(90deg,'+hu.map(x=>'hsl('+Math.round(x*360)+',80%,42%)').join(',')+')':k==='club'?'linear-gradient(90deg,#2a52e0,#8a30e0,#e01fae)':'#3a3d52';
   h+='<div class="srow2"><span class="chip" style="background:'+bg+'"></span><span>'+(k?tr('st_'+k):tr('st_aus'))+'</span><small>'+nf(v[0])+' · '+pct(v[1],v[0])+' % '+tr('stat_done')+'</small><span></span><span style="grid-column:2/4">'+bar(v[1],v[0])+'</span></div>'});
  h+='</div>';
  const cols=(arr,labs,colf)=>{const mx=Math.max(1,...arr);return '<div class="cols">'+arr.map((v,i)=>'<div title="'+labs[i]+': '+nf(v)+'"><small>'+(v?nf(v):'')+'</small><i style="height:'+Math.round(80*v/mx)+'%;background:'+colf(i)+'"></i>'+labs[i]+'</div>').join('')+'</div>'};
  h+='<div class="stc"><h3>'+tr('stat_energy')+'</h3>'+cols(L.e||[],['E1','E2','E3','E4','E5','E6','E7','E8','E9',tr('stat_none')],i=>i<9?ECOL[i]:'#555a70')+'</div>';
  const bl=['&lt;70'];for(let b=70;b<190;b+=10)bl.push(String(b));bl.push('190+');
  h+='<div class="stc"><h3>'+tr('stat_bpm')+'</h3>'+cols(L.bpm||[],bl,()=>'#2f80e0')+'</div>';
  h+='<div class="stc"><h3>'+tr('stat_genres')+'</h3><table>'+(L.g||[]).slice(0,25).map(([g,n,a])=>'<tr><td>'+esc(g)+'</td><td class="n">'+nf(n)+'</td><td class="n">'+pct(a,n)+' %</td></tr>').join('')+'</table></div>'}
 const P=D.played||[];
 h+='<div class="stc"><h3>'+tr('stat_played')+' ('+P.length+')</h3>'+(P.length?'<div class="pl"><table>'+P.map(p=>{const d=new Date(p.t*1000);
   return '<tr><td class="n">'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+'</td><td>'+(p.lvl?'<span class="mxe" style="background:'+(ECOL[Math.min(p.lvl,10)-1]||'#555a70')+'">E'+p.lvl+'</span> ':'')+esc(p.title)+'</td><td class="n">'+esc(p.genre)+(p.style?' → '+tr('st_'+p.style):'')+'</td></tr>'}).join('')+'</table></div>':'<small style="color:#99a">'+tr('stat_noplay')+'</small>')+'</div>';
 box.innerHTML=h}
async function loadHealth(){try{const r=await fetch('/api/health');HL=await r.json();drawHealth()}catch(e){}}
function hlSpark(arr,step,lo,hi,unit,ref){const W=360,H=48,y=v=>H-2-(H-4)*(Math.min(hi,Math.max(lo,v))-lo)/(hi-lo),x=i=>W-(arr.length-1-i);
 const on=arr.map((v,i)=>v===null?null:[x(i),y(v)]).filter(Boolean);if(on.length<2)return '';
 let hit='';const B=12;for(let k=0;k<30;k++){const i=arr.length-1-k*B;if(i<0)break;const v=arr[i];if(v===null)continue;
  hit+='<rect x="'+(x(i)-B)+'" y="0" width="'+B+'" height="'+H+'" fill="transparent"><title>'+tr('hl_ago').replace('#',Math.round((arr.length-1-i)*step/60))+': '+v+' '+unit+'</title></rect>'}
 return '<div class="sp">'+tr('hl_hour')+'<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'+(ref?'<line x1="0" x2="'+W+'" y1="'+y(ref)+'" y2="'+y(ref)+'" stroke="#ff5a4d" stroke-width="1" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>':'')
  +'<polyline fill="none" stroke="#5aa9f0" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke" points="'+on.map(p=>p[0]+','+p[1].toFixed(1)).join(' ')+'"/>'+hit+'</svg><div class="ax"><span>'+tr('hl_ago').replace('#',60)+'</span><span>'+tr('hl_now')+'</span></div></div>'}
function drawHealth(){const D=HL,box=document.getElementById('hlbody'),top=document.getElementById('hlhead');if(!box||!D)return;
 if(!D.t){top.className='';top.innerHTML='<b>'+tr('hl_wait')+'</b>';return}
 const dash='–',nf=(x,d)=>x===null||x===undefined?dash:Number(x).toLocaleString(LANG==='de'?'de-AT':'en-GB',{maximumFractionDigits:d||0,minimumFractionDigits:d||0});
 const dur=s=>{if(s===null||s===undefined)return dash;const m=Math.floor(s/60),h=Math.floor(m/60),t=Math.floor(h/24);return t?t+' d '+(h%24)+' h':h?h+' h '+(m%60)+' min':m+' min'};
 const col={ok:'#2ecc40',warn:'#f0c040',crit:'#ff5a4d'},st=D.st||{};
 const badge=k=>{const s=st[k];return s&&s!=='na'?'<span class="hb '+s+'">'+tr('hl_s_'+s)+'</span>':''};
 const bar=(p,s)=>'<div class="pbar"><i style="width:'+Math.max(0,Math.min(100,p))+'%;background:'+(col[s]||'#2f80e0')+'"></i></div>';
 const row=(a,b)=>'<div class="hr"><span>'+a+'</span><span>'+b+'</span></div>';
 const big=(v,u)=>'<div><b>'+v+'</b><span>'+u+'</span></div>';
 const item=i=>'<li class="'+i.s+'">'+tr(i.k).replace('#',()=>typeof i.v==='number'?nf(i.v,i.k==='hl_i_disk'||i.k==='hl_i_fps'||i.k==='hl_i_work'?1:0):esc(i.v===null||i.v===undefined?'':i.v))+'</li>';
 top.className=D.level;
 top.innerHTML='<b>'+tr('hl_'+D.level)+'</b>'+(D.issues.length?'<ul>'+D.issues.map(item).join('')+'</ul>':'')+'<small>'+tr('hl_pi_up')+' '+dur(D.uptime_s)+' · '+tr('hl_show_up')+' '+dur(D.show_s)+'</small>';
 let h='';const F=D.frames,C=D.cpu,M=D.mem,K=D.disk,P=D.power,L=D.links||{},B=D.backup,H=D.hist||{};
 h+='<div class="stc"><h3>'+tr('hl_frames')+badge('frames')+'</h3>'+(F?'<div class="big">'+big(nf(F.fps,1),tr('hl_fps'))+big(nf(F.work_ms,1),tr('hl_work'))+'</div>'+bar(100*(F.work_ms||0)/25,st.frames)
  +row(tr('hl_late'),nf(F.late_min))+row(tr('hl_late_all'),nf(F.late_total))+row(tr('hl_worst'),nf(F.gap_max_ms)+' ms'):dash)+'</div>';
 h+='<div class="stc"><h3>'+tr('hl_cpu')+badge('cpu')+'</h3>'+(C?'<div class="big">'+big(nf(C.total)+' %',tr('hl_cpu_all'))+'</div>'
  +C.cores.map((v,i)=>'<div class="core"><span>'+tr('hl_core')+' '+(i+1)+'</span>'+bar(v,v>=98?'crit':v>=85?'warn':'')+'<span>'+nf(v)+' %</span></div>').join('')
  +row(tr('hl_load'),C.load.map(x=>nf(x,2)).join(' / ')||dash)+row(tr('hl_clock'),nf(C.mhz)+' / '+nf(C.mhz_max)+' MHz')+row(tr('hl_showcpu'),D.proc_cpu===null?dash:nf(D.proc_cpu)+' % '+tr('hl_onecore'))+row(tr('hl_iowait'),nf(C.iowait)+' %')+hlSpark(H.cpu||[],H.step_s,0,100,'%'):dash)+'</div>';
 h+='<div class="stc"><h3>'+tr('hl_temp')+badge('temp')+'</h3>'+(D.temp!==null?'<div class="big">'+big(nf(D.temp,1)+' °C',tr('hl_tnow'))+big(nf(D.temp_max,1)+' °C',tr('hl_tmax'))+'</div>'+hlSpark(H.temp||[],H.step_s,30,90,'°C',80)+'<div class="sp">'+tr('hl_tlimit')+'</div>':dash)+'</div>';
 h+='<div class="stc"><h3>'+tr('hl_mem')+badge('mem')+'</h3>'+(M?'<div class="big">'+big(nf(M.avail_mb)+' MB',tr('hl_free')+' '+tr('hl_of')+' '+nf(M.total_mb)+' MB')+'</div>'+bar(100*(1-M.avail_mb/M.total_mb),st.mem)
  +row(tr('hl_swap'),nf(M.swap_used_mb)+' / '+nf(M.swap_total_mb)+' MB')+row(tr('hl_showmem'),M.rss_mb===null?dash:nf(M.rss_mb)+' MB ('+(M.rss_grow_mb>=0?'+':'')+nf(M.rss_grow_mb)+' MB '+tr('hl_grow')+')'):dash)+'</div>';
 h+='<div class="stc"><h3>'+tr(K&&K.kind==='sd'?'hl_sd':K&&K.kind==='ssd'?'hl_ssd':'hl_disk')+badge('disk')+'</h3>'+(K?'<div class="big">'+big(nf(K.free_gb,1)+' GB',tr('hl_free')+' '+tr('hl_of')+' '+nf(K.total_gb,1)+' GB')+'</div>'+bar(K.total_gb?100*(1-K.free_gb/K.total_gb):0,st.disk)
  +(K.ro?'<div class="hr"><span></span><span style="color:#ff8a7e">'+tr('hl_ro')+'</span></div>':'')+row(tr('hl_written'),K.written_gb===null?dash:nf(K.written_gb,1)+' GB')
  +row(tr('hl_backup'),!B?dash:B.age_h===null?tr('hl_nobackup'):tr('hl_h_ago').replace('#',nf(B.age_h))):dash)+'</div>';
 const pw=!P?dash:(P.uv_now||P.thr_now)?[P.uv_now?tr('hl_power_uv'):'',P.thr_now?tr('hl_power_thr'):''].filter(Boolean).join(', '):(P.uv_ever||P.thr_ever)?[P.uv_ever?tr('hl_power_uv'):'',P.thr_ever?tr('hl_power_thr'):''].filter(Boolean).join(', ')+' '+tr('hl_power_ever'):tr('hl_power_ok');
 const net=(L.net||[]).map(n=>esc(n.type)+(n.speed?' '+n.speed+' Mbit/s':'')+(n.signal!==null&&n.signal!==undefined?' '+n.signal+' dBm':'')).join(', ')||dash;
 h+='<div class="stc"><h3>'+tr('hl_sys')+badge('sys')+'</h3>'+row(tr('hl_power'),pw)+row(tr('hl_restarts'),nf(D.restarts))
  +row(tr('hl_devices'),!L.known?dash:(L.down||[]).length?tr('hl_notreach')+' '+L.down.map(esc).join(', '):tr('hl_all_reach'))+row(tr('hl_network'),net)
  +row(tr('hl_mixxx'),L.mixxx===null||L.mixxx===undefined?dash:L.mixxx?tr('hl_conn'):tr('hl_noconn'))+row(tr('hl_audio'),nf(L.audio_err_min))+row(tr('hl_send'),nf(L.send_err_min))+'</div>';
 box.innerHTML=h}
if(document.body.classList.contains('vstat')){loadStats();setInterval(()=>{if(!document.hidden)loadStats()},10000)}
if(document.body.classList.contains('vpre')){loadPre();setInterval(()=>{if(!document.hidden)loadPre()},10000)}
if(document.body.classList.contains('vhealth')){loadHealth();setInterval(()=>{if(!document.hidden)loadHealth()},5000)}
const GSTY=['weihnachten','club','party','rock','ruhig'];
async function loadGenres(){try{const r=await fetch('/api/genres');renderGenres(await r.json())}catch(e){}}
function renderGenres(D){const box=document.getElementById('gsed');if(!box||box.contains(document.activeElement))return;
 let h='<div class="sname">'+tr('gs_title')+'</div><div class="sdesc">'+tr('gs_desc')+'</div><div class="gsl">';
 (D.rows||[]).forEach((r,i)=>{const def=r.default?tr('st_'+r.default):tr('st_aus');
  h+='<div class="gsr'+(r.own?' mod':'')+'"><span class="gsn">'+esc(r.genre)+(r.n?' <small>'+r.n+'</small>':'')+'</span><select data-i="'+i+'">'
   +'<option value=""'+(r.own?'':' selected')+'>'+tr('st_def')+' ('+def+')</option>'
   +GSTY.map(s=>'<option value="'+s+'"'+(r.own===s?' selected':'')+'>'+tr('st_'+s)+'</option>').join('')
   +'<option value="aus"'+(r.own==='aus'?' selected':'')+'>'+tr('st_aus')+'</option></select></div>'});
 box.innerHTML=h+'</div>';
 box.querySelectorAll('select').forEach(sel=>sel.onchange=()=>{const r=D.rows[+sel.dataset.i];sel.blur();
  c({genre_style:{genre:r.genre,style:sel.value}}).then(loadGenres)})}
const GEN_GROUPS=['Ausgabe','Haus','Nebel','Titelerkennung','Panel'];   // Gruppen aus settings.py, die unter Einstellungen allgemein stehen
function renderTxEd(T){const box=document.getElementById('txed');if(!box||box.contains(document.activeElement))return;
 let h='<div class="sname">Übersetzungen</div><div class="sdesc">Eigene Texte für Knöpfe, Bereiche und Menüs, auf Deutsch und Englisch. Gilt sofort auf allen Geräten. Ein senkrechter Strich | ist ein Zeilenumbruch auf dem Knopf. Geänderte Felder sind orange, der Pfeil setzt eine Zeile auf den Standard zurück.</div>';
 let cat='';
 T.forEach(t=>{if(t.cat!==cat){cat=t.cat;h+='<div class="txcat">'+esc(cat)+'</div><div class="txhd"><span>Deutsch</span><span>English</span><span></span></div>'}
  const mod=t.de!==t.de0||t.en!==t.en0;
  h+='<div class="txrow'+(mod?' mod':'')+'" data-key="'+esc(t.key)+'"><input data-l="de" value="'+esc(t.de)+'" placeholder="'+esc(t.de0)+'" maxlength="300"><input data-l="en" value="'+esc(t.en)+'" placeholder="'+esc(t.en0)+'" maxlength="300"><button class="sres" title="Auf Standard">&#8634;</button></div>'});
 h+='<div style="margin-top:10px"><button class="sedit" id="txall" style="min-height:38px;padding:6px 12px;background:#3a2a2a">Alle Übersetzungen zurücksetzen</button></div>';
 box.innerHTML=h;
 box.querySelectorAll('.txrow').forEach(r=>{const k=r.dataset.key;
  r.querySelectorAll('input').forEach(i=>i.onchange=()=>{const v=i.value.trim();if(!v){i.value=i.placeholder}c({text_set:{key:k,[i.dataset.l]:v||i.placeholder}}).then(()=>{i.blur();loadTexts()})});
  r.querySelector('.sres').onclick=()=>c({text_reset:k}).then(loadTexts)});
 box.querySelector('#txall').onclick=()=>{if(confirm('Alle Übersetzungen auf den Standard zurücksetzen?'))c({text_reset:'all'}).then(loadTexts)}}
loadSet();
async function loadMusicRoot(){try{const r=await fetch('/api/musik/conf');const d=await r.json();const i=document.getElementById('mroot');if(i&&document.activeElement!==i)i.value=d.root||''}catch(e){}}
async function saveMusicRoot(){const i=document.getElementById('mroot'),st=document.getElementById('mrootst');try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify({op:'music_root_save',root:i.value})});const d=await r.json();if(d.error)throw new Error(d.error);i.value=d.root||'';st.textContent=d.root?'Gespeichert. Die Brücke am Musik-Rechner übernimmt den Ordner innerhalb von 30 Sekunden.':'Gespeichert: leer, es gelten die Pfade aus Mixxx.'}catch(e){st.textContent='Fehler: '+e.message}}
const NL=String.fromCharCode(10);
async function loadNas(d){if(!d){try{d=await (await fetch('/api/musik/conf')).json()}catch(e){return}}const n=d.nas||{};
 [['nashost','host'],['nasmac','mac'],['nasoff','off_at']].forEach(([id,k])=>{const i=document.getElementById(id);if(i&&document.activeElement!==i)i.value=n[k]||''})}
async function saveNas(){const st=document.getElementById('nasst');const v=id=>document.getElementById(id).value.trim();
 try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify({op:'music_nas_save',nas:{host:v('nashost'),mac:v('nasmac'),off_at:v('nasoff')}})});const d=await r.json();if(d.error)throw new Error(d.error);loadNas(d);st.textContent='Gespeichert. Der Musik-Rechner übernimmt die Angaben innerhalb von 30 Sekunden.'}catch(e){st.textContent='Fehler: '+e.message}}
async function ejectStick(){const st=document.getElementById('mejectst');let m='';try{m=(await (await fetch('/api/musik/mac')).json()).music||''}catch(e){}
 if(!m){st.textContent='Der Musik-Rechner ist nicht erreichbar (läuft der Helfer oder die Mixxx-App?).';return}
 if(!confirm('Den Musik-Stick am Musik-Rechner auswerfen? Der Light-Butler hält dafür seine Arbeit am Stick an. Läuft Mixxx mit einem Lied vom Stick, zuerst Mixxx beenden.'))return;
 try{const r=await fetch(m+'/eject',{method:'POST'});const d=await r.json();if(d.error)throw new Error(d.error)}catch(e){st.textContent='Auswerfen: '+e.message;return}
 for(let i=0;i<120;i++){await new Promise(r=>setTimeout(r,1000));let s=null;try{s=await (await fetch(m+'/eject')).json()}catch(e){continue}
  if(s.state==='wait')st.textContent='Halte die Arbeit am Stick an …'+(s.open?' ('+s.open+' Dateien noch offen)':'');
  else if(s.state==='eject')st.textContent='Werfe aus …';
  else if(s.state==='ok'){st.textContent='⏏ Stick ausgeworfen, du kannst ihn abziehen. Steckst du ihn wieder an, arbeitet der Light-Butler von selbst weiter.';return}
  else if(s.state==='err'){st.textContent='⚠ '+(s.error||'Auswerfen ging nicht');return}}
 st.textContent='Auswerfen dauert ungewöhnlich lange. Im Finder nachsehen.'}
async function loadMusicExcl(d){const i=document.getElementById('mexcl');if(!i)return;
 if(!d){try{d=await (await fetch('/api/musik/conf')).json()}catch(e){return}}
 if(document.activeElement!==i)i.value=(d.excl||[]).join(NL);
 const st=document.getElementById('mexclst');if(!(d.excl||[]).length){st.textContent='Keine Ordner ausgeschlossen.';return}
 try{const m=(await (await fetch('/api/musik/mac')).json()).music;if(!m)throw new Error('kein Musik-Rechner');
  const x=await (await fetch(m+'/excl')).json();const mine=JSON.stringify(x.excl||[])===JSON.stringify(d.excl||[]);
  st.textContent=(mine?'':'Der Musik-Rechner übernimmt die Liste in den nächsten 30 Sekunden. ')+(x.rows||[]).map(r=>r.dir+': '+(r.found?r.mp3+' MP3 ausgeschlossen':'Ordner nicht gefunden')).join(' · ')+(x.lib_out?' · aus Mixxx ausgeblendet: '+x.lib_out:'')}
 catch(e){st.textContent='Gespeichert. Den Stand am Musik-Rechner sehe ich erst, wenn die Mixxx-Brücke oder der Helfer läuft.'}}
async function saveMusicExcl(){const i=document.getElementById('mexcl'),st=document.getElementById('mexclst');try{const r=await fetch('/api/sm/cmd',{method:'POST',body:JSON.stringify({op:'music_excl_save',excl:i.value.split(NL)})});const d=await r.json();if(d.error)throw new Error(d.error);i.value=(d.excl||[]).join(NL);st.textContent='Gespeichert. Der Musik-Rechner übernimmt die Liste innerhalb von 30 Sekunden.';setTimeout(()=>loadMusicExcl(),35000)}catch(e){st.textContent='Fehler: '+e.message}}
if(document.body.classList.contains('vset')){loadMusicRoot();loadMusicExcl();loadNas()}
if(document.body.classList.contains('vset')&&location.hash==='#audio')setTimeout(openAudio,300);   // vom Pegelmeter gekommen
if(document.body.classList.contains('vset')&&(location.hash==='#nas'||location.hash==='#musik'))setTimeout(()=>{['genbox','sysbox'].forEach(id=>{const d=document.getElementById(id);if(d)d.open=true});
 const r=document.getElementById(location.hash==='#nas'?'mnasrow':'mrootrow');if(r){r.scrollIntoView({block:'center'});r.style.outline='2px solid #f0a030';r.style.borderRadius='8px';setTimeout(()=>{r.style.outline=''},4000)}},300);   // Spiegel-Seite: direkt zur NAS (11.11.2026)
const GL=[['bar','Spider'],['wash','Washes'],['barlight','PAR Barlicht'],['fx','Eyes und Derby'],['uv','UV-Leiste'],['spot','Moving Head'],['amb','Ambiente'],['nano','Nanoleaf']];
(()=>{const b=document.getElementById('glbody');let h='';
 GL.forEach(([k,l])=>{h+='<div class="glit"><span>'+l+'</span><input type="range" id="gl_'+k+'" min="0" max="100" value="100"><b id="glv_'+k+'">100</b></div>'});
 h+='<button class="glreset" id="gl_reset">Alle auf 100 %</button>';b.innerHTML=h;
 GL.forEach(([k])=>{const s=document.getElementById('gl_'+k);s.oninput=()=>{document.getElementById('glv_'+k).textContent=s.value};s.onchange=()=>c({glevel:{[k]:s.value/100}})});
 document.getElementById('gl_reset').onclick=()=>c({glevel_reset:true})})();
function glToggle(){const p=document.getElementById('glpop'),o=p.style.display==='none';p.style.display=o?'block':'none';
 document.getElementById('glbtn').classList.toggle('on',o);document.getElementById('glarr').textContent=o?'▴':'▾'}
function drawGL(){if(!S.glevel)return;let n=0;
 GL.forEach(([k])=>{const v=Math.round((S.glevel[k]??1)*100);if(v!==100)n++;const s=document.getElementById('gl_'+k),o=document.getElementById('glv_'+k);
  if(s&&document.activeElement!==s){s.value=v;o.textContent=v}if(o)o.classList.toggle('mod',v!==100)});
 document.getElementById('glmod').innerHTML=n?n+'<span class="glw"> '+tr('gl_mod')+'</span>':''}   // Hinweis am Knopf, auch bei geschlossenem Fenster
async function loadBackup(){
 const box=document.getElementById('bkbox');if(!box||!box.open)return;
 try{const r=await fetch('/api/backups');const B=await r.json();const b=document.getElementById('bkbody');
  let h='<div class="ebtn"><button id="bk_now" class="ok">'+(B.info&&B.info.running?'Sicherung läuft ...':'Jetzt sichern')+'</button></div>';
  if(B.info&&B.info.last)h+='<div style="font-size:13px;color:#2ecc40;margin-top:8px">Zuletzt: '+esc(B.info.last)+'</div>';
  if((B.info&&B.info.error)||B.error)h+='<div style="font-size:13px;color:#ff6b5a;margin-top:8px">'+esc((B.info&&B.info.error)||B.error)+'</div>';
  h+='<div style="font-size:13px;color:#aab;margin:10px 0 4px">Vorhandene Sicherungen (neueste zuerst, Ordner '+esc(B.dir||'')+', es bleiben '+esc(B.keep||'')+')</div>';
  h+=(B.items&&B.items.length?B.items.map(i=>'<div style="display:flex;align-items:center;gap:10px;font-family:monospace;font-size:12px;color:#cde;margin:3px 0"><span style="flex:1">'+esc(i.time)+'  '+Math.round(i.size/1024)+' KB</span><a class="sedit" style="min-height:30px;padding:4px 10px;font-family:inherit" href="/backup/'+encodeURIComponent(i.name)+'" download="'+esc(i.name)+'">&#11015; Download</a></div>').join(''):'<small style="color:#889">noch keine</small>');
  h+='<small style="color:#889;display:block;margin-top:8px">Automatisch jede Nacht um 04:30 (nach install_backup.sh). Wiederherstellen: python3 backup.py --restore DATEI.zip. Das Zip enthält den Nanoleaf-Schlüssel, gib es nicht weiter.</small>';
  b.innerHTML=h;document.getElementById('bk_now').onclick=()=>c({backup:true}).then(()=>setTimeout(loadBackup,2500))}catch(e){}}
document.getElementById('bkbox').addEventListener('toggle',loadBackup);setInterval(loadBackup,4000);
let MID=null;
async function loadMidi(){
 const box=document.getElementById('midibox');if(!box||!box.open)return;
 try{const r=await fetch('/api/midi');MID=await r.json();renderMidi()}catch(e){}}
function renderMidi(){
 const b=document.getElementById('midibody');if(!MID){return}
 if(MID.none){b.innerHTML='<small style="color:#889">Nicht aktiv: Der Dienst läuft ohne MIDI (Paket mido fehlt oder --no-midi).</small>';return}
 let h='<div><span class="dot '+(MID.connected?'ok':'bad')+'"></span><b>'+(MID.connected?'verbunden':'nicht verbunden')+'</b> '+(MID.ports&&MID.ports.length?'<small style="color:#889">'+MID.ports.map(esc).join(', ')+'</small>':'')+'</div>';
 if(MID.error)h+='<div style="color:#ff6b5a;font-size:13px;margin-top:4px">'+esc(MID.error)+'</div>';
 if(MID.lumi){const L=MID.lumi,z=L.last&&L.last.length?L.last[L.last.length-1]:null;h+='<div style="margin-top:6px"><span class="dot '+(L.connected?'ok':'bad')+'"></span><b>ROLI Lumi: '+(L.connected?'verbunden':'nicht verbunden')+'</b> '+(L.ports&&L.ports.length?'<small style="color:#889">'+L.ports.map(esc).join(', ')+'</small>':'')+(z?'<small style="color:#889"> · zuletzt '+esc(z.what)+'</small>':'')+' <a href="/lumi" style="color:#9fd0ff;text-decoration:none;font-size:13px">'+tr('apc_page')+' →</a></div>';if(L.error)h+='<div style="color:#ff6b5a;font-size:13px;margin-top:4px">'+esc(L.error)+'</div>'}
 h+='<div style="font-size:13px;color:#aab;margin:6px 0 2px">Pad-Seite: <b style="color:#eee">'+(MID.page===1&&!MID.shift?'Hauptseite':'Farben'+(MID.shift?' (SHIFT)':''))+'</b> · zuletzt gedrückt:</div>';
 h+='<div style="font-family:monospace;font-size:12px;color:#cde;min-height:60px">'+(MID.last&&MID.last.length?MID.last.slice().reverse().map(m=>esc(m.t+'  '+m.what+'  Wert '+m.value+(m.port!==null&&m.port!==undefined?'  (Port '+m.port+')':''))).join('<br>'):'noch nichts')+'</div>';
 if(MID.test_note)h+='<div style="margin-top:8px;font-size:16px;color:#ffb86b"><b>Es leuchtet gerade: Note '+MID.test_note+'</b></div>';
 h+='<div class="ebtn" style="margin-top:8px"><button id="mi_tb">Tasten-Test</button><button id="mi_t1">LED-Test 1-64</button><button id="mi_t2">LED-Test 65-127</button><button id="mi_rd">LEDs neu</button><button id="mi_rl">Belegung neu laden</button></div>';
 h+='<small style="color:#889;display:block;margin-top:6px">LED-Test: Pad n leuchtet in Farbe n. Damit stimmen wir die Farbtabelle ab. Belegung: Datei midimap.json.</small>';
 b.innerHTML=h;
 document.getElementById('mi_tb').onclick=()=>c({midi:{test:3}});document.getElementById('mi_t1').onclick=()=>c({midi:{test:1}});document.getElementById('mi_t2').onclick=()=>c({midi:{test:2}});
 document.getElementById('mi_rd').onclick=()=>c({midi:{redraw:true}});document.getElementById('mi_rl').onclick=()=>c({midi:{reload:true}})}
document.getElementById('midibox').addEventListener('toggle',loadMidi);setInterval(loadMidi,1000);
let AUD=null,audTimer=null;
async function loadAudio(){
 try{const r=await fetch('/api/audio');AUD=await r.json();renderAudio()}catch(e){}}
const LEDS=24;   // je 2,5 dB von -60 bis 0: gruen bis -12,5 dB, gelb bis -2,5 dB, rot darueber (Ziel: Spitzen -12 bis -3 dB)
function ledZone(i){const top=-60+(i+1)*60/LEDS;return top>-2.5?'r':top>-12.5?'y':''}
function ledIdx(db){return db<=-60?-1:Math.min(LEDS-1,Math.ceil((db+60)/(60/LEDS))-1)}
function renderAudio(){
 const b=document.getElementById('audiobody');
 if(!AUD){return}
 if(AUD.sim){b.innerHTML='<small style="color:#889">Im Simulator gibt es keinen Audio-Eingang.</small>';return}
 let h='<label style="font-size:13px;color:#aab">Eingang</label><select id="audev">';
 AUD.devices.forEach(d=>{h+='<option value="'+esc(d.name)+'"'+(d.current?' selected':'')+'>'+esc(d.name)+' ('+d.channels+' Kanäle, '+d.rate+' Hz)</option>'});
 h+='</select><button id="aud_scan" style="margin:6px 0 4px" title="Neu eingesteckte Soundkarten (zum Beispiel USB) finden, ohne den Dienst neu zu starten. Der Ton setzt dabei kurz aus.">Geräte neu suchen</button>';
 if(AUD.net){const n=AUD.net;h+='<div style="font-size:13px;margin:4px 0 6px;color:'+(n.alive?'#9fd0ff':'#ffb86b')+'">'+(n.alive?'<span class="dot ok"></span>Empfängt vom Musik-Rechner ('+esc(n.src)+')'+(n.lost?' · '+n.lost+' Pakete verloren':''):(n.error?esc(n.error):'Wartet auf Ton vom Musik-Rechner: am Mac App „Light-Butler Mixxx“ starten, Ton über BlackHole ausgeben'))+'</div>'}
 if(AUD.error)h+='<div style="color:#ff6b5a;font-size:13px;margin-bottom:6px">'+esc(AUD.error)+'</div>';
 h+='<div class="mnum"><span>Pegel <b id="aud_rms">-</b> · Spitze <b id="aud_pk">-</b><span class="clipb" id="aud_clip">ÜBERSTEUERT</span></span><span id="aud_alive"></span></div>';
 h+='<div class="meter" id="aud_bar">'+Array.from({length:LEDS},(_,i)=>'<i class="'+ledZone(i)+'"></i>').join('')+'</div>';
 h+='<div class="mnum" style="margin-bottom:8px"><span>-60 dB</span><span>-40</span><span>-20</span><span>0 dB</span></div>';
 h+='<div style="font-size:12px;color:#99a;margin-bottom:8px">Ziel: Spitzen etwa zwischen -12 und -3 dB, nie rot. Zu laut: am Mischpult oder Interface leiser stellen, nicht hier.</div>';
 h+='<label style="font-size:13px;color:#aab">Verstärkung (Software) <b id="aud_gv">'+AUD.gain_db+' dB</b></label>';
 h+='<input type="range" id="aud_gain" min="-12" max="24" step="0.5" value="'+AUD.gain_db+'" style="width:100%">';
 h+='<label style="font-size:13px;color:#aab">Kanal</label><div class="seg" id="aud_ch">'+[['mix','Summe'],['left','Links'],['right','Rechts']].map(([k,l])=>'<button data-v="'+k+'"'+(AUD.channel===k?' class="on"':'')+'>'+l+'</button>').join('')+'</div>';
 if(AUD.hw&&AUD.hw.length){h+='<div style="font-size:13px;color:#aab;margin-top:6px">Regler der Soundkarte (Hardware)</div>';
  AUD.hw.forEach((c,i)=>{h+='<label style="font-size:13px;color:#dde">'+esc(c.name)+' <b id="aud_hv'+i+'">'+c.percent+' %</b></label><input type="range" class="aud_hw" data-i="'+i+'" min="0" max="100" step="1" value="'+c.percent+'" style="width:100%">'})}
 if(AUD.rec){const R=AUD.rec;   // Debug-Aufnahme bei Signal (12.11.2026): Knoepfe fest, Stand dahinter
  h+='<div style="margin-top:12px;border-top:1px solid #2a2f45;padding-top:10px"><label style="font-size:13px;color:#aab">Debug-Aufnahme bei Signal</label>';
  h+='<div style="font-size:12px;color:#99a;margin:2px 0 6px">An: Sobald am Eingang Ton über der Stille-Schwelle liegt, nimmt der Light-Butler auf (mit 1 s Vorlauf). Ist 3 s nichts mehr, endet die Datei; beim nächsten Ton beginnt eine neue. Jede fertige Aufnahme wird im Hintergrund zur MP3 (etwa ein Siebtel so groß), die WAV kommt danach weg. Höchstens 10 min je Datei und 1 GB insgesamt, die ältesten fallen dann weg. Nach einem Neustart ist die Aufnahme wieder aus.</div>';
  h+='<div class="seg" id="aud_rec"><button data-v="0"'+(R.on?'':' class="on"')+'>Aus</button><button data-v="1"'+(R.on?' class="on"':'')+'>An</button></div>';
  h+='<div id="aud_recst" style="font-size:13px;margin:6px 0"></div>';
  if(R.files&&R.files.length){h+='<div style="font-size:13px;color:#aab;margin-top:4px">'+R.n+' Aufnahme'+(R.n===1?'':'n')+', '+R.mb+' MB <button id="aud_recdel" class="danger" style="min-height:26px;padding:0 10px;margin-left:6px">Alle löschen</button></div>';
   h+='<div style="max-height:180px;overflow:auto;font-size:13px">'+R.files.map(f=>'<div><a href="/aufnahmen/'+encodeURIComponent(f.name)+'" download>⤓ '+esc(f.name)+'</a> <span style="color:#889">'+Math.round(f.dur)+' s, '+(f.ch==2?'Stereo':f.ch==1?'Mono':f.ch+' Kanäle')+', '+(f.size/1e6).toFixed(1)+' MB'+(f.mp3?', MP3':f.conv?', WAV, wird zur MP3':', WAV')+'</span></div>').join('')+'</div>'}
  const E=R.enc||{};if(R.mp3===false)h+='<div style="font-size:12px;color:#ffb86b;margin-top:4px">Für MP3 fehlt am Pi lame (oder ffmpeg): die Aufnahmen bleiben WAV. Einmal im Terminal: ssh -t admin@'+esc(location.hostname)+' sudo apt-get install -y lame, dann den Dienst neu starten.</div>';
  else if(E.cur||E.wait||E.last||E.err)h+='<div style="font-size:12px;color:#889;margin-top:4px">'+(E.cur?'Wandle '+esc(E.cur)+' zur MP3 …'+(E.wait?' (noch '+E.wait+' danach)':''):'')+(E.last&&E.last.x?(E.cur?' · ':'')+'Zuletzt '+E.last.s+' s gebraucht ('+E.last.x+'-fach schneller als die Aufnahme, niedrigste Priorität)':'')+(E.err?' <span style="color:#ffb86b">'+esc(E.err)+'</span>':'')+'</div>';
  h+='</div>'}
 b.innerHTML=h;
 document.querySelectorAll('#aud_rec button').forEach(bt=>bt.onclick=()=>c({rec:bt.dataset.v==='1'}).then(()=>setTimeout(loadAudio,300)));
 const rd=document.getElementById('aud_recdel');if(rd)rd.onclick=()=>{if(confirm('Alle Debug-Aufnahmen am Light-Butler löschen?'))c({rec_del:true}).then(()=>setTimeout(loadAudio,300))};
 recStat(AUD.rec);
 document.getElementById('aud_scan').onclick=e=>{e.target.disabled=true;e.target.textContent='Suche …';c({audio:{rescan:true}}).then(()=>setTimeout(loadAudio,300)).catch(()=>loadAudio())};
 document.getElementById('audev').onchange=e=>{const v=e.target.value;c({audio:{device:v}}).then(()=>setTimeout(loadAudio,300))};
 const g=document.getElementById('aud_gain');g.oninput=()=>{document.getElementById('aud_gv').textContent=g.value+' dB'};g.onchange=()=>{c({audio:{gain_db:+g.value}})};
 document.querySelectorAll('#aud_ch button').forEach(bt=>bt.onclick=()=>{c({audio:{channel:bt.dataset.v}}).then(()=>{document.querySelectorAll('#aud_ch button').forEach(x=>x.classList.toggle('on',x===bt))})});
 document.querySelectorAll('.aud_hw').forEach(s=>{const i=+s.dataset.i;s.oninput=()=>{document.getElementById('aud_hv'+i).textContent=s.value+' %'};s.onchange=()=>c({audio:{hw:{control:AUD.hw[i].name,percent:+s.value}}})});
}
let recWas=null;
function recStat(r){const el=document.getElementById('aud_recst');if(!el||!r)return;
 el.innerHTML=!r.on?'<span style="color:#889">Aus</span>':r.rec?'<span style="color:#ff6b5a">● Nimmt auf</span> '+Math.round(r.cur_s)+' s'+(r.dropped?' <span style="color:#ffb86b">('+r.dropped+' Blöcke verworfen)</span>':''):'<span style="color:#ffb86b">Wartet auf Ton …</span>';
 if(recWas!==null&&recWas&&!r.rec)setTimeout(loadAudio,500);   // eine Datei ist fertig: Liste neu holen
 recWas=r.rec}
async function audLevel(){
 const box=document.getElementById('audiobox');if(!box||!box.open||!AUD||AUD.sim)return;
 try{const r=await fetch('/api/audio/level');const L=await r.json();if(L.sim)return;
  const bar=document.getElementById('aud_bar');if(!bar)return;
  const n=ledIdx(L.rms_db),pk=ledIdx(L.hold_db);[...bar.children].forEach((e,i)=>{e.classList.toggle('on',i<=n||i===pk);e.classList.toggle('pk',i===pk&&i>n)});
  document.getElementById('aud_rms').textContent=L.rms_db<=-100?'-∞':L.rms_db.toFixed(0)+' dB';
  document.getElementById('aud_pk').textContent=L.hold_db<=-100?'-∞':L.hold_db.toFixed(0)+' dB';
  document.getElementById('aud_clip').style.display=L.clip?'inline-block':'none';
  document.getElementById('aud_alive').textContent=L.alive?'':'kein Signal vom Gerät';
  if(L.rec)recStat(L.rec)}catch(e){}}
document.getElementById('audiobox').addEventListener('toggle',()=>{if(document.getElementById('audiobox').open){loadAudio()}});
setInterval(audLevel,200);
let wowTimer=null;
function wowStart(e){e.preventDefault();try{e.target.setPointerCapture(e.pointerId)}catch(x){}
 c({build:true});clearInterval(wowTimer);wowTimer=setInterval(()=>c({build_keep:true}),400)}
function wowStop(){if(wowTimer===null)return;clearInterval(wowTimer);wowTimer=null;c({build:false})}
// Taster (Strobe, Smoke, Blackout, Blinder, Freeze): nur solange gedrueckt; alle 0,4 s ein Lebenszeichen an die Show,
// sonst laesst sie den Taster nach 1,5 s selbst los (z. B. Handy gesperrt oder Verbindung weg)
const HELD=new Set();let holdTimer=null;
function holdStart(n,e){e.preventDefault();try{e.currentTarget.setPointerCapture(e.pointerId)}catch(x){}if(HELD.has(n))return;HELD.add(n);c({hold:{name:n,on:true}});
 if(!holdTimer)holdTimer=setInterval(()=>{if(HELD.size)c({hold_keep:[...HELD]});else{clearInterval(holdTimer);holdTimer=null}},400)}
function holdStop(n){if(!HELD.has(n))return;HELD.delete(n);c({hold:{name:n,on:false}})}
document.addEventListener('visibilitychange',()=>{if(document.hidden){[...HELD].forEach(holdStop);wowStop()}});
function toggle(k){c({[k]:S.mode!==k})}
function toggleStrobe(){c({strobe:!S.strobe})}
const PW_OFF=['nanoleaf','effektband1','effektband2','derby_bar','musik','nebelmaschine'];let PWSIG=null;
function pwDevs(){return ((S.home&&S.home.devices)||[]).filter(d=>PW_OFF.includes(d.id)&&d.on===true)}
function pwDraw(){const box=document.getElementById('pwdev');if(!box||document.getElementById('pwdlg').style.display==='none')return;
 const L=pwDevs(),sig=L.map(d=>d.id+d.label).join();if(sig===PWSIG)return;PWSIG=sig;
 box.innerHTML=L.length?'<div class="pwl">'+tr('pw_devs')+'</div>'+L.map(d=>'<button data-id="'+esc(d.id)+'">'+esc(d.label)+' '+tr('pw_dev_off')+'</button>').join(''):'';
 box.querySelectorAll('button').forEach(x=>x.onclick=()=>c({home:{id:x.dataset.id,on:false}}))}
function powerOff(){PWSIG=null;document.getElementById('pwdlg').style.display='flex';pwDraw()}
function pwClose(){document.getElementById('pwdlg').style.display='none'}
async function pwGo(){pwClose();await c({poweroff:'JA'});if(!S.powering_off)return;
 const ov=document.createElement('div');ov.style.cssText='position:fixed;inset:0;background:#000e;color:#fff;display:flex;align-items:center;justify-content:center;text-align:center;padding:24px;font-size:19px;line-height:1.5;z-index:99';
 ov.innerHTML=tr('pw_done');document.body.appendChild(ov)}
function drawStrobe(){const sb=document.getElementById('b_strobe');if(!sb)return;sb.innerHTML=tr('strobe_hdr')+' '+tr('strobe_ok')+': '+(S.strobe?tr('yes'):tr('no'));sb.classList.toggle('on',!!S.strobe)}
function bpmMul(f){const base=S.bpm_manual?S.bpm:S.beat_bpm;if(!(base>0))return;c({bpm:Math.round(base*f*10)/10})}
function bpmAdd(d){const base=S.bpm_manual?S.bpm:S.beat_bpm;if(!(base>0))return;c({bpm:Math.round(base)+d})}   // -1 / +1 auf ganze BPM
function tempoToggle(e){e.stopPropagation();const p=document.getElementById('tpop'),o=p.style.display==='none';p.style.display=o?'block':'none';
 document.getElementById('bpmtxt').classList.toggle('open',o)}
document.addEventListener('click',e=>{const p=document.getElementById('tpop');if(p&&p.style.display!=='none'&&!p.contains(e.target)){p.style.display='none';document.getElementById('bpmtxt').classList.remove('open')}});
let TAPS=[];
function tapTempo(e){e.preventDefault();const now=performance.now(),b=document.getElementById('tptap');   // Tap: ab 4 Schlaegen Mittelwert der letzten 8
 if(TAPS.length&&now-TAPS[TAPS.length-1]>2000)TAPS=[];TAPS.push(now);TAPS=TAPS.slice(-8);
 b.classList.add('hit');setTimeout(()=>b.classList.remove('hit'),90);
 if(TAPS.length<4){b.textContent=tr('tap_btn').replace(/<br>/g,' ')+' · '+TAPS.length;return}
 const bpm=Math.round(600000*(TAPS.length-1)/(TAPS[TAPS.length-1]-TAPS[0]))/10;b.textContent=bpm+' BPM';
 if(bpm>=60&&bpm<=200)c({bpm:bpm})}
let aimTimer=null, barSel='all';
function aimsend(){const g=id=>document.getElementById(id);
 g('v_u').textContent=g('s_u').value+' %';g('v_v').textContent=g('s_v').value+' %';g('v_t1').textContent=g('s_t1').value;g('v_t2').textContent=g('s_t2').value;
 clearTimeout(aimTimer);aimTimer=setTimeout(()=>c({aim_set:{vega_u:g('s_u').value/100,vega_v:g('s_v').value/100,bar:barSel,bar_t1:+g('s_t1').value,bar_t2:+g('s_t2').value}}),120)}
const BZ=[1,2,4,5,6.7,10];
function bzi(hz){let b=0;BZ.forEach((v,i)=>{if(Math.abs(v-hz)<Math.abs(BZ[b]-hz))b=i});return b}
(()=>{const b=document.getElementById('blitzhz');BZ.forEach((v,i)=>{const e=document.createElement('button');e.textContent=String(v).replace('.',',');
 e.dataset.i=i;e.onclick=()=>c({blitz_hz:v});b.appendChild(e)})})();
function bdisp(i){const sel=+i;document.querySelectorAll('#blitzhz button').forEach(e=>{const k=+e.dataset.i,cap=!S.strobe&&BZ[k]>3;
  e.classList.toggle('on',k===sel);e.classList.toggle('cap',cap);e.title=cap?TXT.bz_max[LANG==='de'?0:1]:''});   // Hinweis als Tooltip, spart Platz
 document.getElementById('bhz').textContent=''}
function mdisp(v){document.getElementById('mv').textContent=v+' %'}
function mk(id,items,fn,key){const e=document.getElementById(id);if(e.dataset.done)return;e.dataset.done=1;
 items.forEach(([v])=>{const b=document.createElement('button');b.dataset.v=v;b.dataset.tk=id+':'+v;b.innerHTML=tr(b.dataset.tk);b.onclick=()=>fn(v);e.appendChild(b)})}
mk('speed',SPEEDS.filter(x=>x[0]!=='auto'),v=>c({speed:S.speed===v?'auto':v}));   // nochmal tippen = wieder nach der Musik
mk('style',STYB.filter(x=>x[0]!=='auto'),v=>c({style:S.style_man===v?'auto':v}));
document.querySelectorAll('#style button').forEach(b=>{const h=STYHUE[b.dataset.v];   // Knopf in den Farben des Stils
 b.style.background=h?'linear-gradient(90deg,'+h.map(x=>'hsl('+Math.round(x*360)+',80%,42%)').join(',')+')':b.dataset.v==='club'?'linear-gradient(90deg,#2a52e0,#8a30e0,#e01fae,#e02020)':''});
mk('mix',MIXP,v=>c({mix:v}));
mk('move',MOVES,v=>c({move:v}));
mk('color',COLORS.filter(x=>x[0]!=='auto'),v=>c((v==='white'||v==='uv')&&S.color===v?{color:'auto'}:{color_toggle:v}));
document.querySelectorAll('.lk').forEach(e=>e.addEventListener('click',()=>{if(!S.pilot&&!S.sm_show)return;const t=document.getElementById('toast');t.textContent=TXT[S.sm_show?'sm_locked':'pilot_locked'][LANG==='de'?0:1];t.style.opacity=1;clearTimeout(toastT);toastT=setTimeout(()=>{t.style.opacity=0},2500)}));
const CBG={auto:['linear-gradient(90deg,#2a52e0,#8a30e0,#e02020)'],rot:['#d62020'],orange:['#f07800'],gelb:['#f2d400','#222'],
 gruen:['#1fb43c'],cyan:['#0fc0d0','#012'],blau:['#2350ee'],violett:['#8a2fe0'],magenta:['#e01fae'],white:['#f4f4f4','#222'],
 uv:['linear-gradient(135deg,#2a0a5e,#6a1fd0)']};
document.querySelectorAll('#color button').forEach(b=>{const s=CBG[b.dataset.v];if(!s)return;b.classList.add('cb');
 b.style.background=s[0];b.style.color=s[1]||'#fff';if(s[1]==='#222'||s[1]==='#012')b.style.textShadow='none'});
let HOMESIG='';
function drawHome(){const b=document.getElementById('homebody');if(!b)return;const H=S.home;
 if(!H){if(HOMESIG!=='na'){HOMESIG='na';b.innerHTML='<small style="color:#889">'+tr('home_na')+'</small>'}return}
 const sig=JSON.stringify(H.devices.map(d=>[d.id,d.label,d.kind]))+LANG;
 if(sig!==HOMESIG){HOMESIG=sig;let h='',sw='';
  H.devices.forEach(d=>{if(d.kind==='dimmer')h+='<div class="hrow" data-id="'+esc(d.id)+'"><div class="hlab"><span>'+esc(d.label)+'</span><b class="hv">-</b></div><input type="range" min="0" max="100" step="1" class="hsl"><div class="seg" style="margin-top:6px"><button class="hoff">'+tr('off')+'</button><button class="hon">'+tr('on')+'</button></div></div>';
   else sw+='<button data-id="'+esc(d.id)+'" class="hsw">'+esc(d.label)+'<span class="hst"></span></button>'});
  const op=!!(b.querySelector('.hedit')||{}).open;
  b.innerHTML=h+(sw?'<div class="grid">'+sw+'</div>':'')+'<div class="herr"></div><div class="hauto"></div><details class="hedit"'+(op?' open':'')+'><summary>'+tr('home_set_h')+'</summary><div class="hedbody"></div></details>';
  b.querySelectorAll('.hrow').forEach(r=>{const id=r.dataset.id,sl=r.querySelector('.hsl');
   sl.oninput=()=>{r.querySelector('.hv').textContent=sl.value+' %'};sl.onchange=()=>c({home:{id:id,level:sl.value/100}});
   r.querySelector('.hoff').onclick=()=>c({home:{id:id,on:false}});r.querySelector('.hon').onclick=()=>c({home:{id:id,on:true}})});
  b.querySelectorAll('.hsw').forEach(x=>x.onclick=()=>{const d=(S.home.devices||[]).find(v=>v.id===x.dataset.id);c({home:{id:x.dataset.id,on:!(d&&d.on)}})})}
 H.devices.forEach(d=>{if(d.kind==='dimmer'){const r=b.querySelector('.hrow[data-id="'+d.id+'"]');if(!r)return;const sl=r.querySelector('.hsl');
   if(document.activeElement!==sl&&d.level!==null){sl.value=Math.round(d.level*100);r.querySelector('.hv').textContent=sl.value+' %'}
   if(d.ok===false)r.querySelector('.hv').innerHTML=tr('home_unreach');
   r.querySelector('.hon').classList.toggle('on',!!d.on);r.querySelector('.hoff').classList.toggle('on',d.on===false)}
  else{const x=b.querySelector('.hsw[data-id="'+d.id+'"]');if(!x)return;x.classList.toggle('on',!!d.on);x.classList.toggle('unr',d.ok===false);
   x.querySelector('.hst').innerHTML=d.ok===false?tr('home_unreach'):d.on===null?'…':(d.on?tr('on'):tr('off'))}});
 b.querySelector('.herr').textContent=H.error||'';drawHomeAuto(b.querySelector('.hauto'));drawHomeEdit(b.querySelector('.hedbody'))}
function homeKind(k){return tr(k==='dimmer'?'home_dimmer':'home_switch')}
function drawHomeEdit(box){const H=S.home;if(!box||!H)return;
 const sig=JSON.stringify([H.host,H.devices.map(d=>[d.id,d.label,d.addr]),H.found,H.scanning])+LANG;
 if(box.dataset.sig===sig||(box.contains(document.activeElement)&&document.activeElement.tagName==='INPUT'))return;
 box.dataset.sig=sig;const have=new Set(H.devices.map(d=>d.iface+' '+d.addr));
 let h='<div class="hlab"><span>'+tr('home_host')+'</span></div><div class="hed"><input type="text" class="hhost" maxlength="63" value="'+esc(H.host||'')+'"><button class="hhs">'+tr('home_save')+'</button></div>';
 h+='<div class="hlab" style="margin-top:14px"><span>'+tr('home_chan')+'</span></div>';
 H.devices.forEach(d=>{h+='<div class="hed" data-id="'+esc(d.id)+'"><input type="text" class="hlb" maxlength="40" value="'+esc(d.label)+'"><button class="hdel">'+tr('home_del')+'</button></div><small class="had">'+homeKind(d.kind)+' · '+esc(d.iface)+' '+esc(d.addr)+'</small>'});
 h+='<button class="hscan" style="margin-top:10px;width:100%"'+(H.scanning?' disabled':'')+'>'+tr(H.scanning?'home_scanning':'home_scan')+'</button>';
 if(H.found){h+='<div class="hfound">'+(H.found.length?'':'<small>'+tr('home_none')+'</small>');
  H.found.forEach((f,i)=>{const got=have.has(f.interface+' '+f.address);h+='<div class="hed"><span class="hfn">'+esc(f.name)+'<small>'+homeKind(f.kind)+' · '+esc(f.interface)+' '+esc(f.address)+'</small></span><button class="hadd" data-i="'+i+'"'+(got?' disabled':'')+'>'+tr(got?'home_have':'home_add')+'</button></div>'});h+='</div>'}
 box.innerHTML=h;
 box.querySelector('.hhs').onclick=()=>c({home_edit:{host:box.querySelector('.hhost').value}});
 box.querySelectorAll('.hed[data-id]').forEach(r=>{const id=r.dataset.id;
  r.querySelector('.hlb').onchange=e=>c({home_edit:{label:{id:id,text:e.target.value}}});
  r.querySelector('.hdel').onclick=()=>{const d=H.devices.find(v=>v.id===id);if(confirm(TXT.home_del_q[LANG==='de'?0:1]+' '+(d?d.label:id)))c({home_edit:{remove:id}})}});
 box.querySelector('.hscan').onclick=()=>c({home_scan:1});
 box.querySelectorAll('.hadd').forEach(x=>x.onclick=()=>{const f=H.found[+x.dataset.i];c({home_edit:{add:{interface:f.interface,status:f.status}}})})}
function drawHomeAuto(box){const C=S.home_cfg;if(!box||!C)return;
 const sig=C.map(x=>x.key).join()+LANG;
 if(box.dataset.sig!==sig){box.dataset.sig=sig;let h='<div class="hlab" style="margin-top:14px;color:#8ad;font-weight:700"><span>'+tr('home_auto_h')+'</span></div>';
  C.forEach(x=>{if(x.unit.indexOf('switch:')===0)h+='<div class="hrow" data-hk="'+esc(x.key)+'"><div class="hlab"><span>'+tr('ha_'+x.key)+'</span></div><div class="seg"><button data-v="0">'+tr('off')+'</button><button data-v="1">'+tr('on')+'</button></div></div>';
   else h+='<div class="hrow" data-hk="'+esc(x.key)+'"><div class="hlab"><span>'+tr('ha_'+x.key)+'</span><b class="hv"></b></div><input type="range" min="'+x.lo+'" max="'+x.hi+'" step="'+x.step+'"></div>'});
  box.innerHTML=h;
  box.querySelectorAll('.hrow').forEach(r=>{const k=r.dataset.hk,x=C.find(v=>v.key===k);
   r.querySelectorAll('.seg button').forEach(bt=>bt.onclick=()=>c({set:{[k]:+bt.dataset.v}}));
   const sl=r.querySelector('input[type=range]');if(sl){sl.oninput=()=>{r.querySelector('.hv').textContent=fmtHA(+sl.value,x.unit)};sl.onchange=()=>c({set:{[k]:+sl.value}})}})}
 C.forEach(x=>{const r=box.querySelector('.hrow[data-hk="'+x.key+'"]');if(!r)return;
  r.querySelectorAll('.seg button').forEach(bt=>bt.classList.toggle('on',+bt.dataset.v===Math.round(x.value)));
  const sl=r.querySelector('input[type=range]');if(sl&&document.activeElement!==sl){sl.value=x.value;r.querySelector('.hv').textContent=fmtHA(x.value,x.unit)}})}
const FINE={mv:['fan','speed','shift','size'],mx:['fade','speed','shift','size']};
function drawFine(){const F=S.fine;if(!F)return;
 Object.keys(FINE).forEach(g=>{const box=document.getElementById('fine_'+g);if(!box)return;
  if(!box.children.length){FINE[g].forEach(k=>{const d=document.createElement('div');d.dataset.fk=k;
    d.innerHTML='<label><span data-tk="f_'+g+'_'+k+'"></span><b></b></label><input type="range" min="0" max="100" step="1">';
    const sp=d.querySelector('span'),sl=d.querySelector('input'),v=d.querySelector('b');sp.innerHTML=tr(sp.dataset.tk);
    const send=x=>{const a=S.fine&&S.fine[g];if(a)c({fine:{grp:g,btn:a.btn,key:k,v:x}})};
    sl.oninput=()=>{v.textContent=sl.value+' %'};sl.onchange=()=>send(+sl.value);
    sl.ondblclick=()=>{if(sl.disabled)return;sl.value=50;v.textContent='50 %';send(50)};box.appendChild(d)})}
  const a=F[g];box.classList.toggle('off',!a);
  FINE[g].forEach(k=>{const d=box.querySelector('[data-fk="'+k+'"]'),sl=d.querySelector('input');sl.disabled=!a;
   if(document.activeElement!==sl||!a){sl.value=a?Math.round(a.vals[k]):50;d.querySelector('b').textContent=a?sl.value+' %':'–'}})})}
const BEAMS={zoom:100,roll:50,prism:0};
function drawBeam(){const B=S.beam,box=document.getElementById('beam');if(!B||!box)return;
 if(!box.children.length){let h='<button data-tk="beam_auto"></button><div class="bcell"><label><span data-tk="beam_gobo"></span></label><select>';
  for(let i=0;i<6;i++)h+='<option value="'+i+'"'+(i?'>'+i:' data-tk="beam_open">')+'</option>';
  h+='</select></div>';
  Object.keys(BEAMS).forEach(k=>{h+='<div class="bcell" data-bk="'+k+'"><label><span data-tk="beam_'+k+'"></span><b></b></label><input type="range" min="0" max="100" step="1"></div>'});
  box.innerHTML=h;box.querySelectorAll('[data-tk]').forEach(e=>{e.innerHTML=tr(e.dataset.tk)});
  box.querySelector('button').onclick=()=>c({beam:S.beam.auto?{}:'auto'});
  const sel=box.querySelector('select');sel.onchange=()=>c({beam:{gobo:+sel.value}});
  box.querySelectorAll('.bcell[data-bk]').forEach(d=>{const k=d.dataset.bk,sl=d.querySelector('input'),v=d.querySelector('b');
   sl.oninput=()=>{v.textContent=sl.value+' %'};sl.onchange=()=>c({beam:{[k]:+sl.value}});
   sl.ondblclick=()=>{sl.value=BEAMS[k];v.textContent=BEAMS[k]+' %';c({beam:{[k]:BEAMS[k]}})}})}
 box.querySelector('button').classList.toggle('on',!B.auto);box.classList.toggle('bauto',!!B.auto);
 const sel=box.querySelector('select');if(document.activeElement!==sel)sel.value=String(B.vals.gobo);
 box.querySelectorAll('.bcell[data-bk]').forEach(d=>{const k=d.dataset.bk,sl=d.querySelector('input');
  if(document.activeElement!==sl){sl.value=Math.round(B.vals[k]);d.querySelector('b').textContent=sl.value+' %'}})}
let EBSIG='';
function drawEB(){const E=S.eb,g=document.getElementById('ebgrid');if(!E||!g)return;
 const snd=E.sound_ids||[],sig=JSON.stringify([E.names,snd]);
 if(EBSIG!==sig){EBSIG=sig;g.querySelectorAll('button[data-eb]').forEach(b=>b.remove());
  E.names.forEach(([id,n])=>{const b=document.createElement('button');b.dataset.eb=id;b.innerHTML='<small class="ebn">'+id+'</small>'+esc(n)+(snd.includes(id)?' <span class="ebsnd" title="♫">♫</span>':'');
   b.onclick=()=>c({eb_preset:id});g.appendChild(b)})}
 g.querySelectorAll('button[data-eb]').forEach(b=>{const id=+b.dataset.eb;b.classList.toggle('on',E.man===id||(!!S.pilot&&!!E.on&&E.cur===id));
  b.classList.toggle('cur',!!E.on&&E.cur===id&&E.man!==id);b.classList.toggle('sauto',E.auto===id&&!E.man);
  b.disabled=!S.strobe&&E.strobe_ids.includes(id);b.classList.toggle('nosnd',!!E.no_sound&&snd.includes(id));
  b.title=b.classList.contains('nosnd')?(LANG==='de'?'Effektband ohne Ton: dieses soundgesteuerte Preset wählt die Automatik nicht':'Effect strip without sound: the automatic does not choose this sound-reactive preset'):''});}
function drawLvm(){const el=document.getElementById('lvm'),L=S.lvl;if(!el)return;   // kleines Pegelmeter in Zeile 2
 if(!L){el.style.display='none';return}
 el.style.display='flex';const pc=db=>Math.max(0,Math.min(100,(db+60)/60*100));
 el.classList.toggle('dead',!L.alive);el.classList.toggle('clip',!!L.clip&&!!L.alive);
 const r=document.getElementById('lvr'),p=document.getElementById('lvp');
 r.style.width=pc(L.rms_db)+'%';r.style.background=L.peak_db>-3?'#ff5a5a':L.peak_db>-12?'#f0c040':'#3ddc84';
 p.style.left='calc('+pc(L.hold_db)+'% - 1px)';
 document.getElementById('lvs').textContent=S.lvsrc==='lan'?'LAN':'Line-In'}
function powerOn(n){const p=(S.power_for||{})[n];if(!p)return;   // Steckdose eines nicht erreichbaren Geraets (HomeMatic)
 if(confirm(TXT.pwr_q[LANG==='de'?0:1].replace('%s',n).replace('%l',p.label)))c({power_on:n})}
// ---- Seite APC mini · Belegung (/apc) --------------------------------------------------------------------------------
let APCP='pads1',APCSEQ=null;
const APCCMD={auto:'AUTO',blitz:'STROBE',wow:'WOW!',allbright:'BLINDER',freeze:'FREEZE',blackout:'BLACKOUT',fog:'SMOKE',beat:'BPM',laser:'Laser',page1:'Seite 1',page2:'Seite 2',tap:'TAP',beam_auto:'Beam Auto',eb_auto:'Effektband Auto'};
function apcLab(list,v){const x=list.find(e=>e[0]===v);return x?(LANG==='de'?x[1]:x[2]):v}
function apcText(a){if(!a)return tr('apc_free');if(a.cmd)return APCCMD[a.cmd]||a.cmd;if(a.move)return apcLab(MOVES,a.move);
 if(a.mix)return apcLab(MIXP,a.mix);if(a.color)return apcLab(COLORS,a.color);if(a.speed)return a.speed==='auto'?'Speed Auto':apcLab(SPEEDS,a.speed);
 if(a.aim!==undefined)return apcLab(AIMS,a.aim);return '?'}
function apcFlash(id){const e=document.getElementById(id);if(!e)return;e.classList.add('flash');setTimeout(()=>e.classList.remove('flash'),600)}
async function apcTick(){let D;try{D=await (await fetch('/api/apc',{cache:'no-store'})).json()}catch(e){return}
 document.getElementById('apcconn').innerHTML=D.connected?'<span class="dot ok"></span>'+tr('apc_conn')+(D.via==='mac'?' (Musik-Rechner)':''):'<span class="dot"></span>'+tr('apc_noconn');
 document.getElementById('apcpads').innerHTML=D.pages[APCP].map(row=>row.map(c=>{const a=c.act;
  if(!a)return '<div class="apad free" id="n'+c.note+'">'+tr('apc_free')+'</div>';
  const txt=a.scene_index!==undefined||a.scene?(c.nr?'<i>'+c.nr+'</i>':'')+esc(c.scene||'–'):esc(apcText(a));
  const lt=['#c9b52a','#eeeeee','#f0a040','#0fc0d0'].includes(c.color);   // helle Pads: dunkle Schrift
  const bg=c.color?'background:'+c.color+';opacity:'+(0.45+0.55*c.level)+(lt?';color:#1a1a1a;text-shadow:none':''):'';
  return '<div class="apad'+(c.pulse?' pulse':'')+'" id="n'+c.note+'" style="'+bg+'">'+txt+'</div>'}).join('')).join('');
 const btn=b=>'<div class="abtn'+(b.on?' on':'')+(b.act?'':' free')+'" id="n'+b.note+'">'+esc(b.scene||apcText(b.act))+'</div>';
 document.getElementById('apcright').innerHTML=D.right.map(b=>btn(b)).join('');
 document.getElementById('apcbottom').innerHTML=D.bottom.map(b=>btn(b)).join('');
 document.getElementById('apcfaders').innerHTML=D.faders.map(f=>{const a=f.act||{},m=a.fader==='master',g=GL.find(x=>x[0]===a.group);
  const nm=m?'Master':g?g[1]:(f.act?'?':tr('apc_free')),v=f.value===null?0:Math.round(f.value*100);
  return '<div class="afd'+(m?' mst':'')+'" id="cc'+f.cc+'"><div class="tr"><b style="height:'+v+'%"></b></div>'+esc(nm)+'<small>'+(f.value===null?'':v+' %')+'</small></div>'}).join('');
 const L=D.last||[];if(APCSEQ===null)APCSEQ=L.length?L[L.length-1].seq:0;
 L.filter(x=>x.seq>APCSEQ).forEach(x=>{const m=String(x.what).split(' ');if(m[0]==='CC')apcFlash('cc'+m[1]);else if(+m[1]===D.shift_note)apcFlash('apcshift');else apcFlash('n'+m[1])});
 APCD=D;if(APCED){const z=L.filter(x=>x.seq>APCSEQ).pop();if(z){const m=String(z.what).split(' '),n=+m[1],cc=m[0]==='CC';   // Umbelegen: Taste am APC waehlt aus
   if(cc||n!==D.shift_note){document.querySelectorAll('.lumsel').forEach(x=>x.classList.remove('lumsel'));APCSEL={id:(cc?'cc':'n')+n,key:n,sec:cc?'faders':n<64?APCP:'buttons'};apcPickDraw()}}}
 if(L.length)APCSEQ=Math.max(APCSEQ,L[L.length-1].seq);apcMark()}
let APCED=false,APCSEL=null,APCD=null;
function apcMark(){if(APCSEL===null)return;const e=document.getElementById(APCSEL.id);if(e)e.classList.add('lumsel')}
function apcCur(){const D=APCD,S=APCSEL;if(S.sec==='faders')return (D.faders.find(f=>f.cc===S.key)||{}).act;if(S.sec==='buttons')return (D.right.concat(D.bottom).find(b=>b.note===S.key)||{}).act;
 for(const r of D.pages[S.sec])for(const x of r)if(x.note===S.key)return x.act;return null}
function apcPickDraw(){const box=document.getElementById('apcpick'),D=APCD;if(!D)return;if(APCSEL===null){box.textContent=tr('apc_pick');return}
 const a=apcCur(),O=D.options,opt=(id,t,cur)=>'<option value="'+esc(id)+'"'+(id===cur?' selected':'')+'>'+esc(t)+'</option>';let h='';
 if(APCSEL.sec==='faders'){const cur=a?(a.fader==='group'?'group|'+a.group:'fader|'+a.fader):'';
  h='<optgroup label="'+esc(tr('apc_lg_fader'))+'">'+opt('fader|master','Master',cur)+O.group.map(g=>{const x=GL.find(y=>y[0]===g);return opt('group|'+g,x?x[1]:g,cur)}).join('')+'</optgroup>'}
 else{const k=a?Object.keys(a)[0]:'',cur=a?k+'|'+a[k]:'',grp=(tx,kk,vals)=>'<optgroup label="'+esc(tr(tx))+'">'+vals.map(v=>{const o={};o[kk]=v;return opt(kk+'|'+v,apcText(o),cur)}).join('')+'</optgroup>';
  h=grp('lumi_lg_fx','cmd',O.cmd)+grp('lumi_lg_color','color',O.color)+grp('lumi_lg_speed','speed',O.speed)+grp('lumi_lg_move','move',O.move)+grp('lumi_lg_mix','mix',O.mix)
   +'<optgroup label="'+esc(tr('apc_lg_scene'))+'">'+O.scene.map((n,i)=>opt('scene_index|'+i,(i+1)+' '+n,cur)).join('')+'</optgroup>'
   +grp('apc_lg_aim','aim',AIMS.map(x=>x[0]).filter(x=>x))}
 box.innerHTML=esc(APCSEL.sec==='faders'?'CC':tr('lumi_key'))+' '+APCSEL.key+'<select id="apcsel"><option value="">'+esc(tr('lumi_free'))+'</option>'+h+'</select>';
 document.getElementById('apcsel').onchange=async e=>{const v=e.target.value,i=v.indexOf('|'),k=v.slice(0,i),w=v.slice(i+1);let act=null;
  if(v){if(k==='group')act={fader:'group',group:w};else{act={};act[k]=k==='scene_index'?+w:w}}
  await c({apc_key:{sec:APCSEL.sec,key:APCSEL.key,act:act}});await apcTick()}}
if(document.body.classList.contains('vapc')){document.querySelectorAll('#apcpg button').forEach(b=>b.onclick=()=>{APCP=b.dataset.p;
 document.querySelectorAll('#apcpg button').forEach(x=>x.classList.toggle('on',x===b));APCSEL=null;apcTick().then(apcPickDraw)});
 document.getElementById('apcedit').onclick=()=>{APCED=!APCED;APCSEL=null;document.getElementById('apcedit').textContent=tr(APCED?'lumi_done':'lumi_edit');document.getElementById('apcform').style.display=APCED?'block':'none';document.getElementById('apcboard').classList.toggle('edit',APCED);apcTick();apcPickDraw()};
 document.getElementById('apcboard').onclick=e=>{if(!APCED)return;const t=e.target.closest('.apad,.abtn,.afd');if(!t)return;const fd=t.id.startsWith('cc'),key=+t.id.slice(fd?2:1);APCSEL={id:t.id,key:key,sec:fd?'faders':t.classList.contains('apad')?APCP:'buttons'};document.querySelectorAll('.lumsel').forEach(x=>x.classList.remove('lumsel'));apcMark();apcPickDraw()};
 document.getElementById('apcreset').onclick=async()=>{if(!confirm(tr('apc_reset_q')))return;await c({apc_reset:true});APCSEL=null;await apcTick();apcPickDraw()};apcTick();setInterval(apcTick,300)}
// ---- Seite ROLI Lumi · Belegung (/lumi) --------------------------------------------------------------------------------
let LUMIW=0,LUMISEQ=null,LUMID=null,LUMIK='';
const LUMILG=[['color','lumi_lg_color','#e01fae'],['fx','lumi_lg_fx','#f07800'],['speed','lumi_lg_speed','#2e9e4a'],['move','lumi_lg_move','#2b7fd6'],['mix','lumi_lg_mix','#8a2fe0'],['scene','lumi_lg_scene','#12a59a'],['blackout','lumi_lg_black','#8a1414']];
function lumiKey(k,left){const a=k.act,txt=!a?'':k.kind==='scene'?(k.scene||'–'):apcText(a),dk=['#c9b52a','#eeeeee','#f0a040','#0fc0d0'].includes(k.color)?' dk':'',on=a?' on':'',st=k.color?'--k:'+k.color+';':'';
 if(k.black)return '<div class="lumb'+on+dk+'" id="ln'+k.note+'" style="'+st+'left:'+left+'%"><i><span class="lumt">'+esc(txt)+'</span></i></div>';
 return '<div class="lumw'+on+dk+'" id="ln'+k.note+'" style="'+st+'"><span class="lumt">'+esc(txt)+'</span><span class="lumn">'+k.note+'</span></div>'}
let LUMIED=false,LUMISEL=null;
function lumiActKey(a){if(!a)return '';const k=Object.keys(a)[0];return k==='scene_index'?'':k+'|'+a[k]}
function lumiPick(){const box=document.getElementById('lumipick'),D=LUMID;if(!D)return;if(LUMISEL===null){box.textContent=tr('lumi_pick');return}
 const K=D.keys.find(k=>k.note===LUMISEL)||{act:null},O=D.options,cur=K.kind==='scene'?'scene|'+K.scene:lumiActKey(K.act);
 const grp=(tx,k,vals)=>'<optgroup label="'+esc(tr(tx))+'">'+vals.map(v=>{const o={};o[k]=v;const id=k+'|'+v;return '<option value="'+esc(id)+'"'+(id===cur?' selected':'')+'>'+esc(k==='scene'?v:apcText(o))+'</option>'}).join('')+'</optgroup>';
 box.innerHTML=esc(tr('lumi_key'))+' '+LUMISEL+'<select id="lumisel"><option value="">'+esc(tr('lumi_free'))+'</option>'+grp('lumi_lg_color','color',O.color)+grp('lumi_lg_fx','cmd',O.cmd)+grp('lumi_lg_speed','speed',O.speed)+grp('lumi_lg_move','move',O.move)+grp('lumi_lg_mix','mix',O.mix)+grp('lumi_lg_scene','scene',O.scene)+'</select>';
 document.getElementById('lumisel').onchange=async e=>{const v=e.target.value,i=v.indexOf('|');let a=null;if(v){a={};a[v.slice(0,i)]=v.slice(i+1)}
  await c({lumi_key:{note:LUMISEL,act:a}});document.getElementById('lumistale').style.display='block';await lumiTick()}}
function lumiMark(){document.querySelectorAll('.lumsel').forEach(e=>e.classList.remove('lumsel'));if(LUMISEL!==null){const e=document.getElementById('ln'+LUMISEL);if(e)e.classList.add('lumsel')}}
function lumiDraw(){const D=LUMID;if(!D)return;LUMIW=Math.max(0,Math.min(LUMIW,D.windows-1));const lo=D.base+24*LUMIW,keys=D.keys.filter(k=>k.note>=lo&&k.note<lo+24);
 const sig=LUMIW+JSON.stringify(keys);if(sig!==LUMIK){LUMIK=sig;let w=0,h='';keys.forEach(k=>{if(k.black)h+=lumiKey(k,w/14*100);else{h+=lumiKey(k,0);w++}});document.getElementById('lumikeys').innerHTML=h;lumiMark()}
 document.getElementById('lumiwin').textContent=tr('lumi_win')+' '+(LUMIW+1)+' · '+lo+'–'+(lo+23);
 document.getElementById('lumidn').disabled=LUMIW<=0;document.getElementById('lumiup').disabled=LUMIW>=D.windows-1}
async function lumiTick(){let D;try{D=await (await fetch('/api/lumi',{cache:'no-store'})).json()}catch(e){return}LUMID=D;
 document.getElementById('lumiconn').innerHTML=D.connected?'<span class="dot ok"></span>'+tr('apc_conn')+(D.via==='mac'?' (Musik-Rechner)':''):'<span class="dot"></span>'+tr('apc_noconn');
 document.getElementById('lumidot').classList.toggle('ok',D.connected);
 const L=D.last||[];if(LUMISEQ===null)LUMISEQ=L.length?L[L.length-1].seq:0;const neu=L.filter(x=>x.seq>LUMISEQ).map(x=>String(x.what).split(' ')).filter(m=>m[0]==='Note').map(m=>+m[1]);
 if(L.length)LUMISEQ=Math.max(LUMISEQ,L[L.length-1].seq);
 neu.forEach(n=>{const lo=D.base+24*LUMIW;if(n>=D.base&&(n<lo||n>=lo+24))LUMIW=Math.floor((n-D.base)/24)});
 if(LUMIED&&neu.length){LUMISEL=neu[neu.length-1];lumiPick()}   // Umbelegen: Taste am Lumi waehlt aus
   // Taste ausserhalb des Bildes: dorthin wechseln
 lumiDraw();lumiMark();neu.forEach(n=>apcFlash('ln'+n))}
if(document.body.classList.contains('vlumi')){document.getElementById('lumidn').onclick=()=>{LUMIW--;lumiDraw()};document.getElementById('lumiup').onclick=()=>{LUMIW++;lumiDraw()};
 document.getElementById('lumiedit').onclick=()=>{LUMIED=!LUMIED;LUMISEL=null;document.getElementById('lumiedit').textContent=tr(LUMIED?'lumi_done':'lumi_edit');document.getElementById('lumiform').style.display=LUMIED?'block':'none';document.getElementById('lumikeys').classList.toggle('edit',LUMIED);lumiMark();lumiPick()};
 document.getElementById('lumikeys').onclick=e=>{if(!LUMIED)return;const t=e.target.closest('.lumw,.lumb');if(!t)return;LUMISEL=+t.id.slice(2);lumiMark();lumiPick()};
 document.getElementById('lumireset').onclick=async()=>{if(!confirm(tr('lumi_reset_q')))return;await c({lumi_reset:true});LUMISEL=null;document.getElementById('lumistale').style.display='block';await lumiTick();lumiPick()};
 document.getElementById('lumileg').innerHTML=LUMILG.map(g=>'<span><b style="background:'+g[2]+'"></b>'+tr(g[1])+'</span>').join('');lumiTick();setInterval(lumiTick,300)}
function openAutoDJ(e){if(e)e.preventDefault();let w=null;try{w=window.open('','lb_autodj')}catch(x){w=null}   // Auto-DJ im eigenen Fenster: der Ton laeuft beim Seitenwechsel weiter
  if(!w){location.href='/musik/autodj';return}try{if(w.location.pathname!=='/musik/autodj')w.location.href='/musik/autodj'}catch(x){w.location.href='/musik/autodj'}w.focus()}
function openAudio(){if(!document.body.classList.contains('vset')){location.href='/settings#audio';return}   // Pegelmeter: Einstellungen beim Audio-Eingang
 const g=document.getElementById('genbox'),a=document.getElementById('audiobox');
 if(g)g.open=true;if(a){a.open=true;a.scrollIntoView({behavior:'smooth',block:'start'})}}
function drawMxBar(m){const cv=document.getElementById('mxbar');if(!cv)return;
 const W=cv.clientWidth,H=cv.clientHeight,r=window.devicePixelRatio||1;
 if(cv.width!==Math.round(W*r)||cv.height!==Math.round(H*r)){cv.width=Math.round(W*r);cv.height=Math.round(H*r)}
 if(!m||!m.dur){const g0=cv.getContext('2d');g0.setTransform(r,0,0,r,0,0);g0.clearRect(0,0,W,H);   // kein Lied: Platzhalter, gleiche Hoehe
  g0.setLineDash([4,4]);g0.strokeStyle='#3a3d52';g0.lineWidth=1;g0.strokeRect(0.5,0.5,W-1,H-1);g0.setLineDash([]);cv.classList.add('ph');return}
 cv.classList.remove('ph');
 const g=cv.getContext('2d');g.setTransform(r,0,0,r,0,0);g.clearRect(0,0,W,H);
 const X=t=>Math.max(0,Math.min(W,t/m.dur*W)),B=m.bar||{ev:[],en:[]};
 const col={build:'#7a4a1a',gap:'#2a3a6a',break:'#2a3a6a'};
 (B.ev||[]).forEach(e=>{if(e[0]!=='drop'&&col[e[0]]){g.fillStyle=col[e[0]];g.fillRect(X(e[1]),0,Math.max(1,X(e[2])-X(e[1])),H)}});
 const en=B.en||[];if(en.length>1){g.fillStyle='rgba(143,167,216,0.6)';g.beginPath();
  for(let i=0;i<en.length;i++){const x=i/(en.length-1)*W,a=Math.max(0.5,en[i]/100*H*0.45);if(i)g.lineTo(x,H/2-a);else g.moveTo(x,H/2-a)}
  for(let i=en.length-1;i>=0;i--){const x=i/(en.length-1)*W,a=Math.max(0.5,en[i]/100*H*0.45);g.lineTo(x,H/2+a)}g.closePath();g.fill()}
 const scol={intro:'#3f8f9f',vers:'#6b7390',main:'#3fbf6f',outro:'#3f8f9f'};(B.se||[]).forEach(s=>{if(scol[s[0]]){g.fillStyle=scol[s[0]];g.fillRect(X(s[1]),H-3,Math.max(1,X(s[2])-X(s[1])-1),3)}});   // Abschnitte: Streifen unten
 g.fillStyle='#ffd24d';(B.cu||[]).forEach(c=>{const x=X(c);g.fillRect(x-0.5,0,1.5,4);g.fillRect(x-0.5,H-4,1.5,4)});   // Hotcues: kurze gelbe Striche oben und unten
 (B.ev||[]).forEach(e=>{if(e[0]==='drop'){g.fillStyle='#ff4d6d';g.fillRect(X(e[1])-1,0,3,H)}});
 const px=X(m.pos);g.fillStyle='rgba(0,0,0,0.42)';g.fillRect(0,0,px,H);g.fillStyle='#fff';g.fillRect(px-1,0,2,H)}
function fogDown(e){const F=S.fog_st||{};if(F.st==='off'){e.preventDefault();
  if(confirm(TXT.fog_power_q[LANG==='de'?0:1]))c({fog_power:true});return}
 if(F.st==='heat'){e.preventDefault();if(confirm(TXT.fog_cancel_q[LANG==='de'?0:1]))c({fog_power:false});return}holdStart('fog',e)}
function drawFogNote(){const n=document.getElementById('fognote');if(!n)return;const k=S.fog_note||'';n.style.display=k?'flex':'none';
 n.classList.toggle('off',k==='off');if(k)document.getElementById('fogtxt').innerHTML=tr(k==='off'?'fog_note_off':'fog_note_on')}
function drawFog(){const fg=document.getElementById('b_fog');if(!fg)return;const F=S.fog_st||{st:S.fog_on?'fire':'ready',via:'DMX'};
 const mmss=x=>Math.floor(x/60)+':'+String(Math.floor(x%60)).padStart(2,'0');
 const sub={off:'🔌 '+tr('fog_off'),heat:F.wait_sw?tr('fog_waitsw'):tr('fog_heat')+' '+mmss(F.left||0),ready:'<span class="fdot"></span>'+tr('fog_ready')+' · '+esc(F.via||''),
  fire:Math.ceil(F.left||0)+' s',pause:tr('fog_pause')+' '+(F.left||0)+' s',err:'⚠ '+tr('fog_err_'+(F.err||''))}[F.st]||'';
 fg.innerHTML=tr('fog')+'<small>'+sub+'</small>'+((F.st==='heat'||F.st==='pause')?'<span class="fbar" style="width:'+Math.round(Math.max(0,Math.min(1,F.prog||0))*100)+'%"></span>':'');
 ['off','heat','ready','pause','err'].forEach(k=>fg.classList.toggle('fst-'+k,F.st===k));fg.classList.toggle('on',F.st==='fire')}
function fmtHA(v,u){return (u==='s'&&v>=60?Math.floor(v/60)+' min '+(v%60?Math.round(v%60)+' s':''):(Math.round(v*10)/10)+' '+u).trim()}
let AIMEDIT=false,AIMSIG='';
function aimLabel(a){return a.label?esc(a.label):(TXT['aim:'+a.key]?tr('aim:'+a.key):esc(a.key))}
function drawAims(){const L=S.aims||[],box=document.getElementById('aim'),ed=document.getElementById('aim_edit');
 ed.dataset.tx=AIMEDIT?'done':'edit';ed.innerHTML=tr(ed.dataset.tx);ed.classList.toggle('on',AIMEDIT);
 const sig=JSON.stringify(L)+LANG+TXREV+AIMEDIT;
 if(sig!==AIMSIG){AIMSIG=sig;box.innerHTML='';
  [{key:'',label:''}].concat(L).forEach(a=>{const b=document.createElement('button');b.dataset.v=a.key;b.innerHTML=a.key?aimLabel(a):tr('aim:');
   b.onclick=()=>{if(AIMEDIT){if(a.key)c({aim:a.key})}else c({aim:a.key})};box.appendChild(b)});
  if(AIMEDIT){const p=document.createElement('button');p.className='sadd';p.innerHTML=tr('aim_new');
   p.onclick=()=>{const n=prompt(TXT.aim_new_q[LANG==='de'?0:1]);if(n&&n.trim())c({aim_add:n.trim()})};box.appendChild(p)}}
 const eb=document.getElementById('aimed'),cur=L.find(a=>a.key===S.aim);
 if(!AIMEDIT){eb.innerHTML='';eb.dataset.k='';return}
 if(eb.dataset.k===(S.aim||'')+'|'+(cur?cur.label:'')+LANG&&eb.innerHTML)return;
 eb.dataset.k=(S.aim||'')+'|'+(cur?cur.label:'')+LANG;
 if(!cur){eb.innerHTML='<div class="scnote">'+tr('aim_edit_hint')+'</div>';return}
 eb.innerHTML='<div class="sceditor"><label>'+tr('aim_name')+'<input type="text" id="aim_lab" maxlength="30" value="'+(cur.label?esc(cur.label):'')+'" placeholder="'+(TXT['aim:'+cur.key]?esc(TXT['aim:'+cur.key][LANG==='de'?0:1]):'')+'"></label>'+
  '<div class="ebtn" style="display:flex;gap:8px;margin-top:8px"><button class="ok" id="aim_ren">'+tr('aim_rename')+'</button>'+(cur.user?'<button class="del" id="aim_del">'+tr('aim_del')+'</button>':'')+'</div>'+
  '<div class="scnote" style="margin-top:6px">'+(cur.user?'':tr('aim_fixed_hint')+' ')+tr('aim_edit_hint')+'</div></div>';
 document.getElementById('aim_ren').onclick=()=>c({aim_rename:{key:cur.key,label:document.getElementById('aim_lab').value}});
 const del=document.getElementById('aim_del');if(del)del.onclick=()=>{if(confirm(TXT.aim_del_q[LANG==='de'?0:1]))c({aim_delete:cur.key})}}
let SC=[],SCO={},SCREV=-1,EDIT=false,SEL=null;
async function loadScenes(){
 try{const r=await fetch('/api/scenes');const D=await r.json();SC=D.scenes;SCO=D.options;SCREV=D.rev;
 if(SEL&&!SC.find(s=>s.name===SEL))SEL=null;renderScenes()}catch(e){}}
function renderScenes(){
 const pg=document.getElementById('pages');pg.innerHTML='';
 const h=document.createElement('div');h.className='schead';h.innerHTML='<h2 style="margin:0" data-tx="h_scenes">'+tr('h_scenes')+'</h2>';
 const eb=document.createElement('button');eb.className='sedit'+(EDIT?' on':'');eb.dataset.tx=EDIT?'done':'edit';eb.innerHTML=tr(eb.dataset.tx);
 eb.onclick=()=>{EDIT=!EDIT;if(!EDIT)SEL=null;renderScenes()};h.appendChild(eb);pg.appendChild(h);
 if(EDIT){const n=document.createElement('div');n.className='scnote';n.textContent='Szene antippen = bearbeiten. Mit + neue Szene anlegen.';pg.appendChild(n)}
 const g=document.createElement('div');g.className='grid';g.id='scenegrid';
 SC.forEach(s=>{const b=document.createElement('button');b.textContent=s.name;b.dataset.scene=s.name;b.dataset.special=s.special||'';
  if(EDIT&&SEL===s.name)b.classList.add('sel');
  b.onclick=()=>{if(EDIT){SEL=s.name;renderScenes()}else c({scene:s.name})};g.appendChild(b)});
 if(EDIT){const add=document.createElement('button');add.className='sadd';add.textContent='+';add.title='Neue Szene';add.onclick=addScene;g.appendChild(add)}   // nur beim Bearbeiten
 pg.appendChild(g);
 if(EDIT){const rs=document.createElement('div');rs.style.margin='6px 0';
  rs.innerHTML='<button class="sedit" id="sc_reset" style="min-height:38px;padding:6px 12px;background:#3a2a2a" data-tx="sc_reset">'+tr('sc_reset')+'</button>';
  rs.firstChild.onclick=resetScenes;pg.appendChild(rs)}
 if(EDIT&&SEL){const s=SC.find(x=>x.name===SEL);if(s)pg.appendChild(editorFor(s))}
 markScenes()}
function markScenes(){document.querySelectorAll('#scenegrid button[data-scene]').forEach(b=>{const sp=b.dataset.special||'';let on=false;
 if(sp.indexOf('aim:')===0)on=(S.aim===sp.slice(4));else if(sp==='blackout')on=(S.mode==='blackout');else on=(S.mode==='scene'&&S.scene===b.dataset.scene);
 b.classList.toggle('on',on);b.classList.toggle('sauto',!!S.autoscene&&S.autoscene===b.dataset.scene)})}
function addScene(){c({scene_save:{orig:null,scene:{name:'Neue Szene'}}}).then(()=>{EDIT=true;SEL=S.scene_last||null;loadScenes()})}
function editorFor(s){
 const d=document.createElement('div');d.className='sceditor';d.id='sceditor';
 const sp=!!s.special,dis=sp?' disabled':'';
 const sel=(id,list,val)=>'<select id="'+id+'"'+dis+'>'+list.map(([v,l])=>'<option value="'+esc(v)+'"'+(String(v)===String(val)?' selected':'')+'>'+esc(l)+'</option>').join('')+'</select>';
 let h='<div class="edt">Szene bearbeiten'+(sp?' <small>(Spezialszene: nur Name und Position)</small>':'')+'</div>';
 h+='<label>Name<input id="e_name" type="text" maxlength="32" value="'+esc(s.name)+'"></label>';
 if(!sp){
  h+='<label>Licht-Mix'+sel('e_mix',SCO.mixes,s.mix)+'</label><label>Tempo des Licht-Mix'+sel('e_speed',SCO.speeds,s.speed)+'</label>';
  h+='<label>Farbe'+sel('e_color',SCO.colors,s.color)+'</label>';
  h+='<label>Bewegung'+sel('e_move',SCO.moves,s.move)+'</label><label>Bewegungstempo'+sel('e_mspeed',SCO.speeds,s.mspeed)+'</label>';
  h+='<label>Helligkeit <b id="e_levv">'+Math.round(s.level*100)+' %</b><input id="e_level" type="range" min="5" max="100" step="5" value="'+Math.round(s.level*100)+'"></label>';
  h+='<label class="mo mo_strobe">Blitze pro Sekunde <b id="e_hzv">'+s.hz+'</b><input id="e_hz" type="range" min="2" max="12" step="0.5" value="'+s.hz+'"></label>';
  h+='<label class="mo mo_random">Zufall: Lichtpunkte pro Sekunde und Zone <b id="e_ratev">'+s.rate+'</b><input id="e_rate" type="range" min="0.05" max="6" step="0.05" value="'+Math.min(6,s.rate)+'"></label>';
  h+='<label class="mo mo_random">Zufall: Abklingzeit (s) <b id="e_decayv">'+s.decay+'</b><input id="e_decay" type="range" min="0.05" max="3" step="0.05" value="'+s.decay+'"></label>';
  h+='<label class="mo mo_sweep chk"><input id="e_narrow" type="checkbox"'+(s.narrow?' checked':'')+'> schmaler Lichtstreifen</label>';
  const kinds=s.kinds&&s.kinds.length?s.kinds:SCO.kinds.map(k=>k[0]);
  h+='<div class="kinds"><div class="klabel">Welche Lichter machen mit</div>'+SCO.kinds.map(([k,l])=>'<label class="chk"><input type="checkbox" class="e_kind" value="'+k+'"'+(kinds.indexOf(k)>=0?' checked':'')+'> '+esc(l)+'</label>').join('')+'</div>';
  h+='<label>Effektband-Preset'+sel('e_preset',SCO.presets,s.preset)+'</label>';
 }
 h+='<div class="ebtn"><button id="e_save" class="ok">Speichern</button><button id="e_test">Testen</button>'+(sp?'':'<button id="e_dup">Kopie</button>')+'<button id="e_prev">\u25C0 nach vorn</button><button id="e_next">nach hinten \u25B6</button><button id="e_del" class="del">L\u00F6schen</button><button id="e_close">Schlie\u00DFen</button></div>';
 d.innerHTML=h;
 const q=id=>d.querySelector('#'+id);
 const vis=()=>{if(sp)return;const m=q('e_mix').value;d.querySelectorAll('.mo').forEach(e=>e.style.display=e.className.indexOf('mo_'+(m==='strobe'||m==='lightning'?'strobe':m==='random'?'random':m==='sweep'?'sweep':'x'))>=0?'':'none')};
 if(!sp){q('e_mix').onchange=vis;vis();
  [['e_level','e_levv',v=>Math.round(v)+' %'],['e_hz','e_hzv',v=>v],['e_rate','e_ratev',v=>v],['e_decay','e_decayv',v=>v]].forEach(([i,o,f])=>{q(i).oninput=()=>{q(o).textContent=f(+q(i).value)}})}
 const collect=()=>{const v={name:q('e_name').value};
  if(!sp){v.mix=q('e_mix').value;v.speed=q('e_speed').value;v.color=q('e_color').value;v.move=q('e_move').value;v.mspeed=q('e_mspeed').value;
   v.level=+q('e_level').value/100;v.hz=+q('e_hz').value;v.rate=+q('e_rate').value;v.decay=+q('e_decay').value;v.narrow=q('e_narrow').checked;
   v.kinds=[...d.querySelectorAll('.e_kind:checked')].map(x=>x.value);v.preset=+q('e_preset').value}
  return v};
 q('e_save').onclick=()=>c({scene_save:{orig:s.name,scene:collect()}}).then(()=>{SEL=S.scene_last||s.name;loadScenes()});
 q('e_test').onclick=()=>c({scene_save:{orig:s.name,scene:collect()}}).then(()=>{SEL=S.scene_last||s.name;return c({scene:SEL})}).then(loadScenes);
 if(!sp)q('e_dup').onclick=()=>{const v=collect();v.name=v.name+' Kopie';c({scene_save:{orig:null,after:s.name,scene:v}}).then(()=>{SEL=S.scene_last;loadScenes()})};
 q('e_prev').onclick=()=>c({scene_move:{name:s.name,delta:-1}}).then(loadScenes);
 q('e_next').onclick=()=>c({scene_move:{name:s.name,delta:1}}).then(loadScenes);
 q('e_del').onclick=()=>{if(confirm('Szene "'+s.name+'" l\u00F6schen?'))c({scene_delete:s.name}).then(()=>{SEL=null;loadScenes()})};
 q('e_close').onclick=()=>{SEL=null;renderScenes()};
 return d}
function resetScenes(){if(confirm(TXT.sc_reset_q[LANG==='de'?0:1]))c({scenes_reset:true}).then(()=>{SEL=null;loadScenes()})}
loadScenes();
function mark(sel,attr,val){document.querySelectorAll(sel).forEach(b=>b.classList.toggle('on',b.dataset[attr]===val))}
let BT={t:null,period:0};
function beatSync(){
 if(S.beat_ago===null||S.beat_ago===undefined){BT.t=null;return}
 BT.t=performance.now()-S.beat_ago*1000;BT.period=S.beat_bpm>0?60000/S.beat_bpm:0;
 }
function beatLoop(){
 let a=0;
 if(BT.t!==null){let dt=performance.now()-BT.t;
  if(BT.period>0){if(dt>4*BT.period+3000){BT.t=null}else{dt=dt%BT.period;a=Math.exp(-dt/110)}}
  else{a=Math.exp(-dt/150)}}
 document.getElementById('beat').style.opacity=0.12+0.88*a;
 requestAnimationFrame(beatLoop)}
requestAnimationFrame(beatLoop);
let lastNote='',toastT=null;
function slotState(){
 if(S.laser)return['alert laser',tr('ev_laser')];
 if(S.mode==='blackout')return['blk',tr('ev_blackout')];
 if(S.mode==='allbright')return['sun',tr('ev_sun')];
 if(S.build)return['build',tr('wow')+' '+Math.round((S.build_p||0)*100)+' %'];
 if(S.freeze)return['frz',tr('freeze')];
 if(S.blitz)return['alert',tr('ev_blitz')];
 if(S.fog_on)return['fogs',tr('ev_fog')];
 if(S.sm_show)return['smshow',tr('mode_show')];
 if(S.drop)return['drop',tr('ev_drop')];
 if(S.solo)return['alert',tr('ev_solo')+' '+esc(String(S.solo).slice(0,14))];
 if(S.state==='build')return['build',tr('ev_build')];
 if(S.state==='gap')return['gap',tr('ev_gap')];
 if(S.state==='break')return['calm',tr('ev_break')];
 if(S.state==='idle')return['idle',tr('ev_idle')];
 return['idle',tr('ev_normal')]}
function drawHlBtn(){const b=document.getElementById('hlbtn'),l=S.health_level,bad=l==='warn'||l==='crit',t=TXT['hl_'+l];if(!b)return;b.classList.toggle('warn',l==='warn');b.classList.toggle('crit',l==='crit');b.title=bad&&t?t[LANG==='de'?0:1].replace(/:$/,''):'Zustand / Health'}
function sfT(k){const t=TXT[k];return t?(t[LANG==='en'?1:0]||t[0]):k}
function drawSafety(){let o=document.getElementById('sfbox');if(!S.safety_open){if(o)o.remove();return}if(o)return;o=document.createElement('div');o.id='sfbox';o.setAttribute('role','dialog');o.setAttribute('aria-modal','true');o.style.cssText='position:fixed;inset:0;z-index:9999;background:rgba(5,6,10,.82);display:flex;align-items:center;justify-content:center;padding:16px;overflow:auto';const li=['sf_strobe','sf_laser','sf_fog','sf_out','sf_rig'].map(k=>'<li style="margin:6px 0">'+esc(sfT(k))+'</li>').join('');o.innerHTML='<div style="max-width:560px;width:100%;background:#171923;border:1px solid #e8710a;border-radius:12px;padding:18px 20px;font-size:14px;line-height:1.45">'+'<h2 style="margin:0 0 8px;font-size:18px">'+esc(sfT('sf_title'))+'</h2><p style="margin:0 0 6px">'+esc(sfT('sf_intro'))+'</p><ul style="margin:6px 0 10px;padding-left:20px">'+li+'</ul>'+'<p style="margin:0 0 14px;color:#8a90a8">'+esc(sfT('sf_gpl'))+'</p><div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'+'<button id="sfok" style="min-height:40px;padding:0 22px;background:#e8710a;border:0;color:#fff;border-radius:8px;font-weight:600">'+esc(sfT('sf_ok'))+'</button>'+'<a href="/about" style="color:#4aa8ff">'+esc(sfT('sf_more'))+'</a></div></div>';document.body.appendChild(o);document.getElementById('sfok').onclick=()=>{c({safety_ok:1});o.remove()}}
function draw(){drawHlBtn();drawSafety();pwDraw();
 setLang(S.lang);document.body.classList.toggle('nohints',S.ui_hints===false);if(S.texts_rev!==undefined&&S.texts_rev!==TXREV){TXREV=S.texts_rev;loadTexts()}
 beatSync();
 const [cl,tx]=slotState();const sl=document.getElementById('evslot');sl.className=cl;document.getElementById('evtext').innerHTML=tx;
 document.getElementById('bpmnum').textContent=S.bpm_manual&&S.bpm>0?String(Math.round(+S.bpm)):S.beat_bpm>0?String(Math.round(+S.beat_bpm)):'--';   // von Hand: die eingestellte Zahl   // ganze Zahl, Licht rechnet genau
 const bs=document.getElementById('bpmsrc');bs.innerHTML=S.bpm_manual?tr('bpm_manual'):S.tempo_src==='Mixxx'?(S.mx_name||'Mixxx'):'';bs.classList.toggle('man',!!S.bpm_manual);   // Quelle ueber "BPM"
 const R=Object.entries(S.reach||{}),down=R.filter(([n,ok])=>ok===false).map(([n])=>n);
 const poff=(S.power_off||[]).filter(n=>!down.includes(n)),warnl=down.concat(poff);   // dazu: Steckdose aus (Derby und Bar, Musik)
 const modeTxt={show:TXT.mode_show[LANG==='de'?0:1]+' '+S.sm_show,auto:(S.pilot?TXT.auto:TXT.mode_manual)[LANG==='de'?0:1],scene:TXT.mode_scene[LANG==='de'?0:1]+' '+S.scene,blackout:TXT.mode_blackout[LANG==='de'?0:1],allbright:TXT.mode_allbright[LANG==='de'?0:1]}[S.mode]||'';
 const KEN={Cis:'C#',Es:'Eb',Fis:'F#',As:'Ab',B:'Bb',H:'B'},kp=String(S.key||'').split('-');
 const kl=S.key?(LANG==='de'?kp[0]+'-':(KEN[kp[0]]||kp[0])+' ')+(kp[1]==='Moll'?TXT.key_minor:TXT.key_major)[LANG==='de'?0:1]:'';
 const keyTxt=S.key?(S.key_sure?'<b>'+esc(kl)+'</b>':'<span style="color:#889">'+esc(kl)+'?</span>')+(S.key_src==='Mixxx'?'<span class="srcb">'+(S.mx_name==='Auto-DJ'?'AUTO-DJ':'MIXXX')+'</span>':''):'';   // Marke auf der Grundlinie, Zeile huepft nicht
 const meterTxt=S.meter?(S.meter_conf>=0.35?esc(S.meter):'<span style="color:#889">'+esc(S.meter)+'?</span>')+(S.bar_len===3?' <b style="color:#f0a030">'+tr('st_meter3')+'</b>':''):'';
 const mt=modeTxt.length>20?modeTxt.slice(0,19)+'…':modeTxt;
 document.getElementById('r2l').innerHTML=(S.mode==='show'?['<b class="modeb">'+esc(mt)+'</b>']:S.state==='idle'?['<b class="modeb">'+esc(mt)+'</b>','<span style="color:#9fd0ff">'+tr('st_silence')+'</span>']:['<b class="modeb">'+esc(mt)+'</b>',(TXT['tier'+S.tier]?tr('tier'+S.tier):tr('st_tier')+' '+S.tier),TXT['mood:'+S.mood]?tr('mood:'+S.mood):esc(S.mood),keyTxt,meterTxt]).filter(Boolean).join(' · ');
 const wr=document.getElementById('warnrow'),wbtn=(cl,tip,cmd,t)=>'<span class="wc '+cl+'" title="'+tip+'" onclick="'+cmd+'">'+t+'</span>',
  wh=warnl.map(n=>{const t=esc(n)+(poff.includes(n)?' '+tr('pwr_off'):'');return (S.power_for||{})[n]?'<u class="wc pwr" data-pw="'+esc(n)+'" title="Antippen = Steckdose einschalten">⏻ '+t+'</u>':'<span class="wc">'+t+'</span>'}).join('')+(S.dmx_debug?'<a class="wc" href="/dmx-debug">'+tr('w_dmxdebug')+'</a>':'')+(S.sm_show?'<a class="wc i" href="/shows">'+tr('w_show')+': '+esc(S.sm_show)+'</a>':'')+(S.artin&&S.artin.active?wbtn('i','Antippen = Art-Net-Eingang aus','c({set:{artnet_in:0}})',tr('w_artin')):'')+(S.fx_pending?wbtn('i','Fixture-Änderungen warten auf den Neustart','fxRestart()',tr('w_restart')):'')+(S.ola_out===false&&S.ola_have!==false?wbtn('o','Antippen = einschalten','c({set:{ola_out:1}})',tr('w_dmx')):'')+(S.wled_out===false&&S.wled_have!==false?wbtn('o','Antippen = einschalten','c({set:{wled_out:1}})',tr('w_wled')):'')+(S.nano_present&&S.nano_out===false&&S.nano_have!==false?wbtn('o','Antippen = einschalten','c({set:{nano_out:1}})',tr('w_nano')):'');
 const wfull=wh||(S.mode?'<span class="wok">✓ '+tr('w_allok')+'</span>':'');   // erst mit echten Daten, nicht beim Verbinden
 if(wr.dataset.h!==wfull){wr.dataset.h=wfull;wr.innerHTML=wfull;wr.querySelectorAll('[data-pw]').forEach(e=>e.onclick=()=>powerOn(e.dataset.pw))}   // nur bei Aenderung: Wischen und Tippen bleiben ungestoert
 drawLvm();
 document.getElementById('ola_off').classList.toggle('on',S.ola_out===false&&S.ola_have!==false);document.getElementById('ola_on').classList.toggle('on',S.ola_out!==false&&S.ola_have!==false);document.getElementById('ola_none').classList.toggle('on',S.ola_have===false);
 document.getElementById('dmxmon').href='/dmx?lang='+LANG;
 document.getElementById('artin_off').classList.toggle('on',!S.artin);document.getElementById('artin_on').classList.toggle('on',!!S.artin);
 (()=>{const a=S.artin,el=document.getElementById('artinst');if(!a){el.innerHTML='';return}
  el.innerHTML=a.error==='dry'?'<span style="color:#889">'+tr('usb_e_dry')+'</span>':a.error?'<span class="dot bad"></span><span style="color:#ffb86b">'+esc(a.error)+'</span>':a.active?'<span class="dot ok"></span><span style="color:#9fd0ff">'+tr('artin_rx')+' '+esc(a.src)+'</span>':'<span style="color:#889">'+tr('artin_wait')+'</span>'})();
 document.getElementById('via_ola').classList.toggle('on',S.dmx_via!=='usb');document.getElementById('via_usb').classList.toggle('on',S.dmx_via==='usb');
 (()=>{const u=S.dmx_usb,el=document.getElementById('usbst');if(!u){el.innerHTML='';return}
  el.innerHTML=u.ok?'<span class="dot ok"></span><span style="color:#9fd0ff">'+esc(u.port)+' · '+u.channels+' '+tr('usb_ch')+'</span>':'<span class="dot bad"></span><span style="color:#ffb86b">'+tr('usb_e_'+(u.err||'wait'))+(u.detail?' ('+esc(u.detail)+')':'')+'</span>'})();
 document.getElementById('wled_off').classList.toggle('on',S.wled_out===false&&S.wled_have!==false);document.getElementById('wled_on').classList.toggle('on',S.wled_out!==false&&S.wled_have!==false);document.getElementById('wled_none').classList.toggle('on',S.wled_have===false);
 document.getElementById('nanorow').style.display=S.nano_present?'block':'none';
 (()=>{const L=S.link||{};document.getElementById('link_off').classList.toggle('on',!S.link_on);document.getElementById('link_on').classList.toggle('on',!!S.link_on);
  document.getElementById('linkst').innerHTML=!L.available?tr('link_na')+' '+esc(L.error||''):L.on?'· '+tr('link_sends')+' '+(+L.tempo).toFixed(2)+' BPM '+tr('link_to')+' '+L.peers+' '+(L.peers===1?tr('link_dev1'):tr('link_devn')):esc(L.error||'')})();
 document.getElementById('nano_off').classList.toggle('on',S.nano_out===false&&S.nano_have!==false);document.getElementById('nano_on').classList.toggle('on',S.nano_out!==false&&S.nano_have!==false);document.getElementById('nano_none').classList.toggle('on',S.nano_have===false);
 drawLyric();drawCover();
 (()=>{const m=S.mx,el=document.getElementById('mxline');
  const fm=x=>(+x).toFixed(1).replace('.',',');
  const nm={drop:tr('mx_drop'),build:tr('mx_build'),gap:tr('mx_gap')};
  const mst=m=>m.status_key?tr(m.status_key):esc(m.status);
  const dot=c=>'<span class="dot '+c+'"></span>';
  const row=(d,l,mid,right)=>d+'<span class="mxl">'+l+'</span><span class="mxn">'+mid+'</span><span class="mxs">'+right+'</span>';
  if(!m||!m.connected||m.deck===null)drawMxBar(null);
  const s=S.sr;el.title='';
  if(s&&(!m||!m.connected||m.deck===null||(!m.plan&&s.title))){   // kein Lied aus Mixxx: die Titelerkennung nimmt dieselbe Zeile
   const bad=s.st==='missing'||s.st==='error'||s.st==='offline',st=S.style_eff?tr('st_'+S.style_eff):'',arrow=st&&st.toLowerCase()!==String(s.genre).toLowerCase()?' → '+st:'';
   if(m&&m.connected&&m.deck!==null)drawMxBar(m);
   el.style.display='';el.title=s.msg||'';el.innerHTML=row(dot(s.title?'ok':(bad?'bad':'')),'<b>'+tr('sr_label')+'</b><i>'+(S.lvsrc==='lan'?'LAN':'Line-In')+'</i>',s.title?'<span style="color:#9fd0ff;font-weight:600;font-size:12.5px">'+(s.artist?esc(s.artist)+' – ':'')+esc(s.title)+'</span>':'<span style="color:#889">'+tr('sr_'+s.st)+'</span>',s.title&&s.genre?'<span style="color:#889;font-weight:400;font-size:12px">'+esc(s.genre)+arrow+'</span>':'');return}
  const MXOFF=document.documentElement.classList.contains('nomixxx');el.style.display='';   // ohne Mixxx (14.11.2026): Zeile nur fuer den Auto-DJ
  if(MXOFF&&(!m||!m.connected||m.deck===null||(m.deck!==11&&m.deck!==12))){el.innerHTML='';el.style.display='none';return}
  if(!m){el.innerHTML=row('','<span style="color:#889">Mixxx</span>','<span style="color:#889">'+tr('mx_off')+'</span>','');return}
  if(!m.connected){el.innerHTML=row(dot(''),'<b>Mixxx</b>','<span style="color:#889">'+tr('mx_noconn')+'</span>','');return}
  if(m.deck===null){el.innerHTML=row(dot('ok'),'<b>Mixxx</b>','<span style="color:#889">'+mst(m)+'</span>','');return}
  const tag='';const dcl=m.plan?(m.use?'ok':'info'):'ok';
  let mid,right='';
  const ms=x=>Math.floor(x/60)+':'+String(Math.floor(x%60)).padStart(2,'0');
  const tt=m.el!=null&&m.tot!=null?'<span class="mxtot">'+ms(m.el)+' / '+ms(m.tot)+'</span>':'';
  const lt=tt+(m.left!=null?'<span class="mxleft" style="color:#ccd;font-weight:600;font-variant-numeric:tabular-nums;margin-right:6px">−'+ms(m.left)+'</span>':'');
  if(m.plan){mid=(m.lvl?'<span class="mxe" style="background:'+(ECOL[Math.min(m.lvl,10)-1]||'#555a70')+'"'+(m.lvl_est?' title="geschätzt"':'')+'>E'+m.lvl+(m.lvl_est?'~':'')+'</span>':'')+'<span class="mxn2" style="color:#9fd0ff;font-weight:600;font-size:12.5px">'+esc(m.title||'')+'</span>'+(m.genre?'<span class="mxg">'+esc(m.genre)+(m.style&&tr('st_'+m.style).toLowerCase()!==String(m.genre).toLowerCase()?' → '+tr('st_'+m.style):'')+'</span>':'');
   right=(m.next||[]).length?'<span class="mxsv" style="color:#ffb86b;font-weight:700">'+(m.next||[]).map(x=>nm[x.type]+' '+fm(x.in)).join(' · ')+' s</span>':'<span style="color:#889">'+tr('mx_noevent')+'</span>'}
  else mid='<span style="color:#889">'+mst(m)+'</span>';
  const ad=m.src==='autodj';   // Auto-DJ im Browser als Quelle (08.11.2026): Decks A und B statt 11 und 12
  el.innerHTML=row(dot(dcl),'<b>'+(ad?'Auto-DJ':'Mixxx')+'</b> '+tr('mx_deck')+' '+(ad?(m.deck===11?'A':'B'):m.deck)+tag,mid,lt+(right?' '+right:''));drawMxBar(m)})();
 (()=>{const net=S.net||[],nup=net.filter(n=>n.up).length,ok=R.filter(([n,v])=>v===true).length;
  const bad=down.length>0||(net.length&&!nup);
  document.getElementById('syssum').innerHTML='<span class="dot '+(bad?'bad':'ok')+'"></span>'+tr('m_sys')+' · '+ok+' '+tr('sys_of')+' '+R.length+' '+tr('sys_reach')+(down.length?' ('+down.map(esc).join(', ')+' '+tr('sys_missing')+')':'')+(S.ola_out===false?' · <b style="color:#ffb86b">'+tr('sys_dmx_off')+'</b>':'')+(S.wled_out===false?' · <b style="color:#ffb86b">'+tr('sys_wled_off')+'</b>':'')+(S.nano_present&&S.nano_out===false?' · <b style="color:#ffb86b">'+tr('sys_nano_off')+'</b>':'');
  document.getElementById('net').innerHTML=net.map(n=>{
   const dc=n.up?'ok':(n.present?'bad':'');
   let txt='<span class="dot '+dc+'"></span><b>'+esc(n.type)+'</b> ';
   if(n.up){txt+=esc(n.ip);
    if(n.type==='LAN'&&n.speed)txt+=' · '+n.speed+' Mbit/s';
    if(n.type==='WLAN'){if(n.ssid)txt+=' · '+esc(n.ssid);
     if(n.signal!==null&&n.signal!==undefined){const q=n.signal>=-60?'sg':n.signal>=-70?'sm':'sw';txt+=' · <span class="'+q+'">'+n.signal+' dBm</span>'}
     if(n.band)txt+=' · '+esc(n.band)}}
   else txt+=n.type==='LAN'?'<span style="color:#889">kein Kabel / keine Verbindung</span>':'<span style="color:#889">nicht verbunden</span>';
   if(n.main&&n.up)txt+='<span class="mainc">Hauptverbindung</span>';
   return '<span class="nb">'+txt+'</span>'}).join('');
  document.getElementById('reach').innerHTML=R.map(([n,ok])=>'<span><span class="dot '+(ok===true?'ok':ok===false?'bad':'')+'"></span>'+esc(n)+((S.reach_ip||{})[n]?' <small style="color:#889">'+((S.reach_url||{})[n]&&ok===true?'<a class="cfgl" href="'+esc(S.reach_url[n])+'" target="_blank" rel="noopener">'+esc(S.reach_ip[n])+'</a>':esc(S.reach_ip[n]))+'</small>':'')+'</span>').join('')})();
 const nt=S.note||'';
 if(nt&&nt!==lastNote){const t=document.getElementById('toast');t.textContent=nt;t.style.opacity=1;clearTimeout(toastT);toastT=setTimeout(()=>{t.style.opacity=0},3500)}
 lastNote=nt;
 (b=>{b.classList.toggle('on',!!S.pilot||!!S.sm_show);const t=S.sm_show?tr('mode_show'):tr('auto');if(b.textContent!==t)b.textContent=t})(document.getElementById('b_auto'));document.documentElement.classList.toggle('pilot',!!S.pilot||!!S.sm_show);
 document.getElementById('b_black').classList.toggle('on',S.mode==='blackout');
 document.getElementById('b_sun').classList.toggle('on',S.mode==='allbright');
 drawFog();drawFogNote();
 document.getElementById('b_freeze').classList.toggle('on',!!S.freeze);
 const bb=document.getElementById('b_build');bb.innerHTML=S.build?tr('wow')+'<br>'+Math.round((S.build_p||0)*100)+' %':tr('wow');bb.classList.toggle('on',!!S.build);
 const bl=document.getElementById('b_blitz');bl.innerHTML=tr('blitz');bl.classList.toggle('on',!!S.blitz);
 bdisp(bzi(S.blitz_hz));
 drawStrobe();
 (()=>{const det=S.beat_bpm>0?(+S.beat_bpm).toFixed(1):'--';   // Tempo-Fenster
  document.getElementById('tpdet').textContent=tr('tempo_detected')+': '+det.replace('.',',')+(S.tempo_src==='Mixxx'?' ('+(S.mx_name||'Mixxx')+')':' (Audio)');
  document.getElementById('tpval').textContent=S.bpm_manual?String(S.bpm).replace('.',','):(S.beat_bpm>0?String(Math.round(+S.beat_bpm)):'--');
  document.getElementById('tpman').textContent=S.bpm_manual?tr('bpm_manual'):'';
  document.getElementById('bpm_auto').classList.toggle('on',!S.bpm_manual)})();
 if(document.activeElement.id!=='master'){document.getElementById('master').value=Math.round(S.master*100);mdisp(Math.round(S.master*100))}
 drawAims();drawHome();drawFine();drawBeam();drawEB();mark('#aim button','v',S.aim||'');
 const as=document.getElementById('aimset');as.style.display=S.aim?'block':'none';
 if(S.aim&&S.aim_vals&&!document.activeElement.id.startsWith('s_')){const g=id=>document.getElementById(id),a=S.aim_vals;
  const bp=a.bars[barSel]||a.bars.all;
  const ca=(S.aims||[]).find(x=>x.key===S.aim);g('aimname').innerHTML=ca?aimLabel(ca):esc(S.aim);g('s_u').value=Math.round(a.vega_u*100);g('s_v').value=Math.round(a.vega_v*100);g('s_t1').value=bp[0];g('s_t2').value=bp[1];
  g('v_u').textContent=g('s_u').value+' %';g('v_v').textContent=g('s_v').value+' %';g('v_t1').textContent=bp[0];g('v_t2').textContent=bp[1];
  const bs=document.getElementById('barsel');if(bs.dataset.n!==Object.keys(a.bars).join()){bs.dataset.n=Object.keys(a.bars).join();bs.innerHTML='';
   Object.keys(a.bars).forEach(k=>{const b=document.createElement('button');b.innerHTML=k==='all'?tr('aim_all'):esc(k.replace('docooler_','D'));b.dataset.bar=k;b.style.cssText='margin:2px;padding:8px 12px;min-height:0';b.onclick=()=>{barSel=k;draw()};bs.appendChild(b)})}
  bs.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.bar===barSel))}
 mark('#mix button','v',S.mixbtn||'');mark('#speed button','v',S.speed);mark('#style button','v',S.style_man||'auto');document.querySelectorAll('#style button').forEach(b=>b.classList.toggle('eff',S.style_man==='auto'&&b.dataset.v===S.style_eff));mark('#move button','v',S.move);document.querySelectorAll('#color button').forEach(b=>b.classList.toggle('on',b.dataset.v===S.color||(S.colors||[]).includes(b.dataset.v)));
 markScenes();drawGL();
 if(S.scene_rev!==undefined&&S.scene_rev!==SCREV&&!document.getElementById('sceditor'))loadScenes();
}
async function poll(){try{const r=await fetch('/api/state');S=await r.json();draw()}catch(e){const wr=document.getElementById('warnrow');if(wr){wr.dataset.h='';wr.innerHTML=''}const se=document.getElementById('st');if(se)se.textContent='Keine Verbindung'}}
poll();setInterval(poll,500);
</script><script src="/static/sm/core.js"></script><script src="/static/sm/nav.js"></script></body></html>"""


def make_page():
    return (PAGE.replace("__MIXP__", json.dumps([list(x) for x in MIX_PANEL if x[0] in MIX_BUTTONS]))
            .replace("__MOVES__", json.dumps(MOVES)).replace("__COLORS__", json.dumps(COLORS))
            .replace("__SPEEDS__", json.dumps(SPEEDS)).replace("__AIMS__", json.dumps(AIMS))
            .replace("__STYB__", json.dumps(STYLE_BTNS)).replace("__STYHUE__", json.dumps({k: v["colors"] for k, v in STYLES.items()}))
            .replace("__TEXTS__", json.dumps({k: [de, en] for k, _, de, en in catalog()}, ensure_ascii=False)))


# ---- Fixture-Ansicht: Kanalbeschreibungen --------------------------------------------------------
DESC = {
    "docooler_90w": {"tilt1": "Tilt 1 (Zelle 1)", "tilt2": "Tilt 2 (Zelle 2)", "dimmer": "Dimmer gesamt", "strobe": "Strobe",
                     "r1": "Zelle 1 Rot", "g1": "Zelle 1 Gruen", "b1": "Zelle 1 Blau", "w1": "Zelle 1 Weiss",
                     "w2": "Zelle 2 Weiss", "b2": "Zelle 2 Blau", "g2": "Zelle 2 Gruen", "r2": "Zelle 2 Rot",
                     "reset": "Reset (nie ueber 199!)"},
    "led_4in1_rgbuv": {"mode": "Betriebsart (5 = direkte Steuerung)", "colorwheel": "Farbvorwahl", "speed": "Programm-Geschwindigkeit",
                       "dimmer": "Master-Dimmer", "r": "Rot", "g": "Gruen", "b": "Blau", "uv": "UV"},
    "vega_spot_60": {"pan": "Pan (Schwenken)", "pan_fine": "Pan fein (uPan)", "tilt": "Tilt (Neigen)", "tilt_fine": "Tilt fein (uTilt)",
                     "pt_speed": "Pan/Tilt-Geschwindigkeit", "dimmer": "Dimmer", "shutter": "Shutter (255 = offen)",
                     "colorwheel": "Farbrad", "gobo": "Gobo", "gobo_rot": "Gobo-Rotation", "zoom": "Zoom",
                     "prism": "Prisma", "auto_play": "Auto Play (nur 0-7 erlaubt)", "auto_run": "Auto Run (nur 0-7 erlaubt)",
                     "speed_mode": "Speed Mode (max. 50)"},
    "laser_ktv": {"power": "Ein/Aus (0 = aus)", "group": "Effektgruppe (je 32 Werte eine, ab 192 Animationen)",
                  "effect": "Effektauswahl (je 6 Werte ein Effekt)", "color": "Musterfarbe (10 rot, 17 gruen, 27 blau)",
                  "color_speed": "Farbgeschwindigkeit", "auto": "Auto 0-127 / Sound-to-Light ab 128"},
    "eyes_21": {"mode": "Betriebsart", "laser_red1": "Laser Rot 1", "laser_red2": "Laser Rot 2", "laser_green": "Laser Gruen",
                "laser_blue": "Laser Blau", "motor_speed": "Motor-Geschwindigkeit", "uv": "UV", "led_r": "LED Rot",
                "led_g": "LED Gruen", "led_b": "LED Blau", "flash": "Flash / Strobe"},
    "par_rgbw_8ch": {"dimmer": "Dimmer", "r": "Rot", "g": "Gruen", "b": "Blau", "w": "Weiss", "strobe": "Strobe",
                     "function": "Funktion (max. 50)", "func_speed": "Funktions-Geschwindigkeit"},
    "derby_4in1_15ch": {"dimmer": "Dimmer", "strobe_a": "Strobe A", "r": "Rot", "g": "Gruen", "b": "Blau", "w": "Weiss",
                        "laser_red": "Laser Rot", "laser_green": "Laser Gruen", "strobe_b": "Strobe B", "led_motor": "LED-Motor",
                        "laser_motor": "Laser-Motor", "laser_red8": "Laser Rot 8", "laser_effect": "Laser-Effekt",
                        "mode": "Betriebsart", "speed": "Geschwindigkeit"},
    "buv463_uv": {"dimmer": "Dimmer", "strobe": "Strobe", "auto": "Auto-Programm (max. 50)", "auto_speed": "Auto-Geschwindigkeit",
                  "uv1": "UV Reihe 1", "uv2": "UV Reihe 2", "uv3": "UV Reihe 3", "uv4": "UV Reihe 4"},
    "hazer": {"pump": "Pump Output (Nebelmenge)", "fan": "Fan Speed (Luefter)"},
    "wled_drgb": {"dimmer": "Helligkeit", "r": "Rot", "g": "Gruen", "b": "Blau"},
    "wled_preset": {"dimmer": "Helligkeit", "preset": "WLED-Preset (Nummer)"},
}


def backup_file(name, cfg=None):
    """Pfad einer Sicherung zum Herunterladen, nur wenn der Name genau in der Liste der Sicherungen steht
    (kein Zugriff auf andere Dateien). Sonst None."""
    try:
        import backup
        cfg = cfg or backup.load_conf()
        names = {i["name"] for i in backup.list_backups(cfg)}
    except Exception:                                   # noqa: BLE001
        return None
    name = unquote(str(name))
    if name not in names:
        return None
    return os.path.join(cfg["dir"], name)


# ---- Handbuch (Hilfe-Knopf) ---------------------------------------------------------------------------------------
ICON_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS = {"/icon.svg": ("icon.svg", "image/svg+xml"),                      # Browser-Tab (Light-Butler, Butler serviert Licht)
         "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),  # Home-Bildschirm iPad/iPhone (180 px)
         "/favicon.ico": ("apple-touch-icon.png", "image/png")}           # aeltere Browser fragen ohne Link danach
ICON_LINKS = ('<link rel="icon" type="image/svg+xml" href="/icon.svg"><link rel="apple-touch-icon" href="/apple-touch-icon.png">'
              '<meta name="apple-mobile-web-app-title" content="Light-Butler"><meta name="theme-color" content="#16171f">')


def icon_file(path):
    """(Inhalt, Typ) eines Icons oder None."""
    if path not in ICONS:
        return None
    name, ctype = ICONS[path]
    try:
        with open(os.path.join(ICON_DIR, name), "rb") as f:
            return f.read(), ctype
    except OSError:
        return None


HELP_FILES = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "HANDBUCH.md"),          # auf dem Pi (deploy.sh)
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "HANDBUCH.md")]  # im Projekt
HELP_FILES_EN = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "MANUAL_EN.md"),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "MANUAL_EN.md")]
# Technische Beschreibung (15.11.2026): das fruehere ausfuehrliche Handbuch, Seite /help/technik, Link oben im Handbuch
TECH_FILES = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "TECHNIK.md"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "TECHNIK.md")]
TECH_FILES_EN = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "TECHNICAL_EN.md"),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "TECHNICAL_EN.md")]
# Eigene Seite "Meine Anlage" (Adressen, Geraete, Raum der eigenen Anlage; nur am eigenen Licht-Rechner, nie in Paketen
# oder auf GitHub). Gibt es die Datei, zeigt das Handbuch oben einen Link darauf (/help/anlage).
ANLAGE_FILES = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "MEINE_ANLAGE.md"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "MEINE_ANLAGE.md")]


def _md_inline(text):
    """Text maskieren, dann `Code` und **fett**."""
    t = html_escape(text.replace("&#91;", "[").replace("\\]", "]").replace("\\[", "["))
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    return t


def markdown_to_html(md):
    """Kleiner Umwandler fuer das Handbuch: Ueberschriften, Absaetze, Listen, Tabellen, fett, Code und Code-Bloecke
    (ohne Zusatzpakete).
    Gibt (HTML, Inhaltsverzeichnis [(Anker, Titel)]) zurueck."""
    out, toc, para, lst, table, code = [], [], [], None, [], None

    def flush():
        nonlocal para, lst, table
        if para:
            out.append("<p>" + " ".join(_md_inline(x) for x in para) + "</p>")
            para = []
        if lst:
            out.append(f"<{lst[0]}>" + "".join(f"<li>{_md_inline(x)}</li>" for x in lst[1]) + f"</{lst[0]}>")
            lst = None
        if table:
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table]
            body = [r for r in rows[1:] if not all(re.fullmatch(r":?-{3,}:?", c) for c in r)]
            out.append("<div class=\"tw\"><table><tr>" + "".join(f"<th>{_md_inline(c)}</th>" for c in rows[0]) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</table></div>")
            table = []

    for line in md.splitlines():
        s = line.rstrip()
        if s.startswith("```"):                        # Code-Block (Befehle): unveraendert, nur maskiert
            if code is None:
                flush()
                code = []
            else:
                out.append("<pre><code>" + html_escape("\n".join(code)) + "</code></pre>")
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            anchor = "k%d" % len(out)
            if level == 2:
                toc.append((anchor, title))
            out.append(f"<h{level} id=\"{anchor}\">{_md_inline(title)}</h{level}>")
        elif s.startswith("|"):
            if para or lst:
                flush()
            table.append(s)
        elif re.match(r"^\s*[-*]\s+", s) or re.match(r"^\s*\d+\.\s+", s):
            kind = "ol" if re.match(r"^\s*\d+\.", s) else "ul"
            if para or table or (lst and lst[0] != kind):
                flush()
            lst = lst or (kind, [])
            lst[1].append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", s))
        elif not s.strip():
            flush()
        elif re.match(r"^!\[[^\]]*\]\((\.\./pi)?/static/[a-z_/]+\.svg\)$", s):   # Bild aus pi/static (Schema im Handbuch)
            flush()
            alt, src = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", s).groups()
            src = src[len("../pi"):] if src.startswith("../pi/") else src     # ../pi/static/... (stimmt auch auf GitHub)
            out.append(f'<p class="img"><img src="{html_escape(src)}" alt="{html_escape(alt)}"></p>')
        elif "embedded content" in s:
            flush()
            out.append("<p class=\"emb\">" + _md_inline(s) + "</p>")
        else:
            if lst or table:
                flush()
            para.append(s.strip())
    flush()
    return "\n".join(out), toc


def anlage_file():
    return next((p for p in ANLAGE_FILES if os.path.isfile(p)), None)


def help_page(lang="de", anlage=False, technik=False):
    """Das Handbuch als eigene Seite (Hilfe-Knopf im Panel), auf Deutsch (HANDBUCH.md) oder Englisch (MANUAL_EN.md).
    Fehlt die englische Fassung, kommt die deutsche. anlage=True: die Seite "Meine Anlage" (MEINE_ANLAGE.md).
    technik=True: die ausfuehrliche Technische Beschreibung (TECHNIK.md, TECHNICAL_EN.md)."""
    en = lang == "en"
    md = None
    if anlage:
        files = [anlage_file()] if anlage_file() else []
    elif technik:
        files = TECH_FILES_EN + TECH_FILES if en else TECH_FILES
    else:
        files = HELP_FILES_EN + HELP_FILES if en else HELP_FILES
    for p in files:
        try:
            with open(p, encoding="utf-8") as f:
                md = f.read()
            break
        except OSError:
            continue
    cover = ""
    if md is None:
        body, toc = (("<p>The manual (MANUAL_EN.md) was not found. It is copied to the Pi with <code>./deploy.sh push</code>.</p>" if en else
                      "<p>Das Handbuch (HANDBUCH.md) wurde nicht gefunden. Es wird mit <code>./deploy.sh push</code> auf den Pi kopiert.</p>"), [])
    else:
        cover, sep, rest = md.partition("\n## ")         # Deckblatt: Titel bis zum ersten Kapitel, wie im PDF des Showmanagers
        if sep and cover.lstrip().startswith("# "):
            lines = [x.strip() for x in cover.strip().splitlines() if x.strip()]
            cover = ("<div class=\"cover\"><h1>" + _md_inline(lines[0][2:]) + "</h1><i class=\"bar\"></i>"
                     + "".join(f"<p class=\"c{min(i, 3)}\">{_md_inline(x)}</p>" for i, x in enumerate(lines[1:], 1)) + "</div>")
            body, toc = markdown_to_html("## " + rest)
        else:
            cover = ""
            body, toc = markdown_to_html(md)
    nav = "".join(f"<a href=\"#{a}\">{_md_inline(t)}</a>" for a, t in toc)
    if not anlage and anlage_file():                     # eigene Anlage: Link oben im Inhaltsverzeichnis
        nav = f"<a href=\"/help/anlage\"><b>{'My system' if en else 'Meine Anlage'}</b></a>" + nav
    lq = "en" if en else "de"
    if technik:                                          # zurueck zum kurzen Handbuch
        nav = f"<a href=\"/help?lang={lq}\"><b>{'User manual' if en else 'Benutzerhandbuch'}</b></a>" + nav
    elif not anlage:                                     # Link zur ausfuehrlichen Technischen Beschreibung
        nav = f"<a href=\"/help/technik?lang={lq}\"><b>{'Technical description' if en else 'Technische Beschreibung'}</b></a>" + nav
    return (f"<!doctype html><html lang=\"{'en' if en else 'de'}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>Light-Butler - {('Technical description' if en else 'Technische Beschreibung') if technik else ('Manual' if en else 'Handbuch')}</title>{ICON_LINKS}<style>"
            ":root{color-scheme:dark}body{margin:0;background:#12131c;color:#dde;font:15px/1.55 -apple-system,Segoe UI,sans-serif;padding:14px 16px 40px;max-width:900px;margin:0 auto}"
            "h1{font-size:22px;color:#fff}h2{font-size:18px;color:#8ad;margin:28px 0 8px;padding-top:8px;border-top:1px solid #262a36}h3,h4{font-size:15px;color:#cde}"
            "code{background:#222536;border-radius:4px;padding:1px 5px;font-size:13px;color:#ffd38a}b{color:#fff}"
            "pre{background:#222536;border-radius:8px;padding:10px 12px;overflow-x:auto}pre code{padding:0;background:none}"
            ".tw{overflow-x:auto}table{border-collapse:collapse;margin:8px 0;font-size:14px}th,td{border:1px solid #2f3346;padding:5px 8px;text-align:left;vertical-align:top}th{background:#1c1f2c;color:#9fd0ff}"
            "nav{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 4px}nav a{background:#222536;color:#9fd0ff;border-radius:14px;padding:4px 10px;font-size:13px;text-decoration:none}"
            ".cover{background:#14161f;border:1px solid #262a36;border-radius:12px;padding:26px 22px 18px;margin:10px 0 6px}.cover h1{font-size:30px;margin:0}"
            ".cover .bar{display:block;width:46px;height:4px;background:#df7a2c;border-radius:2px;margin:10px 0 14px}.cover p{margin:4px 0}.cover .c1{font-size:16px;color:#a8acba}"
            ".cover .c2{margin-top:22px;color:#a8acba}.cover .c2 b{font-size:17px}.cover .c3{margin-top:14px;padding-top:10px;border-top:1px solid #2c2f42;color:#889;font-style:italic;font-size:13px}"
            ".img img{display:block;width:100%;max-width:680px;height:auto;margin:10px 0}.emb{color:#778;font-style:italic;font-size:13px}.top{position:fixed;right:12px;bottom:12px;background:#2a2c3d;color:#9fd0ff;border-radius:50%;width:40px;height:40px;display:flex;align-items:center;justify-content:center;text-decoration:none;font-size:20px}"
            "</style></head><body><div class=\"s2lnav\" data-back=\"/\" data-cur=\"help\" data-title=\"h_help\">"
            f"{'Help' if en else 'Hilfe'}</div>{cover}<nav>{nav}</nav>{body}<a class=\"top\" href=\"#\" title=\"{'to top' if en else 'nach oben'}\">&uarr;</a><script src=\"/static/sm/nav.js\"></script></body></html>")


# Texte der Kopfleiste (static/sm/nav.js): Titel der Seiten und die Menuepunkte
NAV_KEYS = ("nav_back", "nav_home", "nav_menu", "music_host", "h_showman", "h_music", "h_autotag", "h_dupes", "h_titles", "h_check", "h_genres", "h_cd", "h_folders", "h_import", "h_merge", "h_lose", "h_mirror", "h_fnametags", "h_care", "h_pre", "h_autodj", "h_artists", "h_albums", "h_favs", "h_missing", "h_damaged", "h_groups", "h_room", "stat_title", "h_health", "h_setpage", "h_software", "h_about",
            "h_help", "h_editor", "h_fixtures", "apc_title", "lumi_title", "h_dmxdebug", "sys_dmxmon")


def nav_info(show):
    """Sprache des Panels und die Texte der Kopfleiste (mit den eigenen Texten aus der Uebersetzungstabelle)."""
    m = show.texts.merged()
    return {"lang": "en" if show.cfg["ui_lang"] > 0.5 else "de", "texts": {k: m[k] for k in NAV_KEYS if k in m}}


ABOUT_KEYS = ("sf_intro", "sf_strobe", "sf_laser", "sf_fog", "sf_out", "sf_rig")
LICENSE_FILES = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "LICENSE"),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "LICENSE")]


def program_stand(base=None):
    """Stand der Programme fuer die Seite Ueber: Datum der juengsten Programmdatei (*.py) als JJJJ-MM-TT."""
    base = base or os.path.dirname(os.path.abspath(__file__))
    t = 0.0
    for d in (base, os.path.join(base, "showman")):
        try:
            for n in os.listdir(d):
                if n.endswith(".py"):
                    t = max(t, os.path.getmtime(os.path.join(d, n)))
        except OSError:
            pass
    return time.strftime("%Y-%m-%d", time.localtime(t)) if t else ""


def about_info(show):
    """Seite Ueber Light-Butler (/about): Sprache, Stand, Sicherheitstexte (mit eigenen Texten)."""
    m = show.texts.merged()
    return {"lang": "en" if show.cfg["ui_lang"] > 0.5 else "de", "stand": program_stand(),
            "texts": {k: m[k] for k in ABOUT_KEYS if k in m}}


def dmx_state(show, target=None):
    """DMX-Monitor: das zuletzt gesendete Bild eines Ziels (512 Kanaele) mit den Fixtures darauf."""
    rig, out = show.rig, show.output
    main = rig.target
    via = "USB" if show.cfg["dmx_via"] > 0.5 else "Art-Net-Gateway"
    targets = [{"id": main, "label": f"DMX ({via})"}]
    for t in rig.targets():
        if t == main or str(t).startswith("nanoleaf:"):
            continue
        names = [f.extra.get("label", f.name) for f in rig.fixtures if f.target == t]
        targets.append({"id": t, "label": f"{', '.join(names) or t} ({t})"})
    t = target if any(x["id"] == target for x in targets) else main
    data = out.last_sent.get(t) if out is not None and hasattr(out, "last_sent") else None
    if data is None:
        data = rig.render_all().get(t, bytes(512))
    fx = []
    for f in sorted((f for f in rig.fixtures if (f.target or main) == t), key=lambda f: f.address):
        inv = {ch: p for p, ch in f.map.items()}
        fx.append({"name": f.name, "label": f.extra.get("label", f.name), "start": f.address, "n": f.n,
                   "params": [inv.get(c, "") for c in range(1, f.n + 1)]})
    ext = out is not None and hasattr(out, "ext_active") and out.ext_active() and t == main
    return {"target": t, "targets": targets, "data": list(bytes(data)[:512]) + [0] * max(0, 512 - len(data)),
            "sending": True if out is None else out.is_sending(t), "src": "artnet" if ext else "show", "fixtures": fx}


DMX_PAGE = r"""<!doctype html><html lang="%LANG%"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Light-Butler - DMX-Monitor</title>%ICONS%<style>
:root{color-scheme:dark}body{margin:0;background:#12131c;color:#dde;font:14px/1.4 -apple-system,Segoe UI,sans-serif;padding:12px 14px 30px}
a{color:#9fd0ff;text-decoration:none}h1{font-size:18px;margin:8px 0}
#bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:8px}select{background:#222536;color:#dde;border:1px solid #333a50;border-radius:6px;padding:5px}
#st{color:#9fd0ff}#info{min-height:20px;color:#ffd38a;margin:4px 0 8px}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(42px,1fr));gap:3px}
.c{position:relative;border-radius:4px;padding:2px 3px 3px;text-align:center;background:#1a1c28;border:1px solid #23263a;cursor:pointer}
.c small{display:block;font-size:9px;color:#778;text-align:left}.c b{font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}
.c.fa{border-color:#3a4a66}.c.fb{border-color:#5a4a33}.c.st{border-left:3px solid #9fd0ff}.c.z b{color:#556}
.c i{position:absolute;right:2px;top:1px;font-size:8px;font-style:normal;color:#9fd0ff;max-width:80%;overflow:hidden;white-space:nowrap}
</style></head><body><div class="s2lnav" data-back="/settings" data-cur="settings" data-title="sys_dmxmon">DMX-Monitor</div>
<div id="bar"><select id="tgt"></select><label><input type="checkbox" id="used"> <span id="usedl"></span></label><span id="st"></span></div>
<div id="info"></div><div id="grid"></div>
<script>
const EN=document.documentElement.lang==='en';
const T=EN?{used:'only channels in use',show:'from the show',art:'from Art-Net input (external)',off:'output off',ch:'Channel',free:'not assigned',tap:'Tap a channel for details.'}
 :{used:'nur belegte Kanäle',show:'von der Show',art:'vom Art-Net-Eingang (extern)',off:'Ausgabe aus',ch:'Kanal',free:'nicht belegt',tap:'Kanal antippen für Details.'};
document.getElementById('usedl').textContent=T.used;document.getElementById('info').textContent=T.tap;
let tgt='',sig='',owner=[],cells=[],sel=null;
function build(d){const g=document.getElementById('grid');g.innerHTML='';owner=new Array(513).fill(null);cells=[];
 d.fixtures.forEach((f,k)=>{for(let i=0;i<f.n;i++){const a=f.start+i;if(a<=512)owner[a]={f:f,k:k,p:f.params[i],i:i}}});
 const only=document.getElementById('used').checked;
 for(let a=1;a<=512;a++){const o=owner[a];if(only&&!o)continue;const e=document.createElement('div');
  e.className='c'+(o?(o.k%2?' fb':' fa')+(o.i===0?' st':''):'');e.dataset.a=a;
  e.innerHTML='<small>'+a+'</small><b>0</b>'+(o&&o.i===0?'<i>'+o.f.label.replace(/[<>&]/g,'')+'</i>':'');
  e.onclick=()=>{sel=a;show(d)};g.appendChild(e);cells[a]=e}}
function show(d){if(sel===null)return;const o=owner[sel],v=d.data[sel-1];
 document.getElementById('info').textContent=T.ch+' '+sel+' = '+v+' ('+Math.round(v/2.55)+' %) · '+(o?o.f.label+' · '+(o.p||'?')+' ('+T.ch+' '+(o.i+1)+')':T.free)}
async function tick(){try{const r=await fetch('/api/dmx'+(tgt?'?t='+encodeURIComponent(tgt):''),{cache:'no-store'});const d=await r.json();
 const s=document.getElementById('tgt');const ts=JSON.stringify(d.targets);
 if(s.dataset.sig!==ts){s.dataset.sig=ts;s.innerHTML=d.targets.map(x=>'<option value="'+x.id+'">'+x.label.replace(/[<>&"]/g,'')+'</option>').join('');s.value=d.target}
 const k=d.target+'|'+JSON.stringify(d.fixtures)+'|'+document.getElementById('used').checked;if(k!==sig){sig=k;build(d)}
 for(let a=1;a<=512;a++){const e=cells[a];if(!e)continue;const v=d.data[a-1];const b=e.querySelector('b');
  if(b.textContent!==String(v)){b.textContent=v;e.style.background=v?'rgba(255,154,46,'+(0.12+0.7*v/255).toFixed(2)+')':'';e.classList.toggle('z',!v)}}
 document.getElementById('st').textContent=d.sending?(d.src==='artnet'?T.art:T.show):T.off;show(d)}catch(e){document.getElementById('st').textContent='…'}}
document.getElementById('tgt').onchange=e=>{tgt=e.target.value;sig=''};document.getElementById('used').onchange=()=>{sig=''};
tick();setInterval(tick,250);
</script><script src="/static/sm/nav.js"></script></body></html>"""


def apc_page():
    """APC mini als Grafik (Einstellungen -> MIDI-Controller, selber Tab): dasselbe Panel, nur #apcsec."""
    return (make_page().replace("<title>Light-Butler</title>", "<title>Light-Butler - APC mini</title>", 1)
            .replace("</style></head><body>", "</style></head><body class=\"vapc\">", 1))


def lumi_page():
    """ROLI Lumi als Grafik (Einstellungen, selber Tab): dasselbe Panel, nur #lumisec."""
    return (make_page().replace("<title>Light-Butler</title>", "<title>Light-Butler - ROLI Lumi</title>", 1)
            .replace("</style></head><body>", "</style></head><body class=\"vlumi\">", 1))


def stats_page():
    """Seite Statistik (runder Knopf neben dem Zahnrad, selber Tab): dasselbe Panel, nur #statsec."""
    return (make_page().replace("<title>Light-Butler</title>", "<title>Light-Butler - Statistik</title>", 1)
            .replace("</style></head><body>", "</style></head><body class=\"vstat\">", 1))


def pre_page():
    """Seite Vorab-Laeufe (Wunsch 12.11.2026, aus der Statistik in die Datenpflege): Liedtexte, Cue-Punkte, Cover und Spur-Kurven
    vorab holen. Dasselbe Panel, nur #presec; erreichbar ueber die Datenpflege (letzter Schritt)."""
    return (make_page().replace("<title>Light-Butler</title>", "<title>Light-Butler - Vorab-Läufe</title>", 1)
            .replace("</style></head><body>", "</style></head><body class=\"vpre\">", 1))


def health_page():
    """Seite Zustand (Herz neben dem Statistik-Knopf, selber Tab): dasselbe Panel, nur #hlsec."""
    return (make_page().replace("<title>Light-Butler</title>", "<title>Light-Butler - Zustand</title>", 1)
            .replace("</style></head><body>", "</style></head><body class=\"vhealth\">", 1))


def settings_page():
    """Die Einstellungen auf eigener Seite (Zahnrad oben, im selben Tab, "Panel" fuehrt zurueck): dasselbe Panel, nur #setsec."""
    return (make_page().replace("<title>Light-Butler</title>", "<title>Light-Butler - Einstellungen</title>", 1)
            .replace("</style></head><body>", "</style></head><body class=\"vset\">", 1))


def fixtures_page():
    """Die Fixtures auf eigener Seite (wie DMX-Monitor und Hilfe): dasselbe Panel, nur der Bereich Fixtures sichtbar."""
    return (make_page().replace("<title>Light-Butler</title>", "<title>Light-Butler - Fixtures</title>", 1)
            .replace("</style></head><body>", "</style></head><body class=\"vfx\">", 1))


def dmx_page(lang="de"):
    return DMX_PAGE.replace("%LANG%", "en" if lang == "en" else "de").replace("%ICONS%", ICON_LINKS)


def fixtures_info(rig):
    """Statische Beschreibung aller Fixtures mit allen Kanaelen (fuer die Fixture-Ansicht im Panel)."""
    out = []
    nano = [f for f in rig.fixtures if f.group == "nano"]
    for f in sorted([f for f in rig.fixtures if f.group != "nano"], key=lambda f: (f.extra.get("nr", 999), f.address)):
        inv = {ch: p for p, ch in f.map.items()}
        chans = []
        for ch in range(1, f.n + 1):
            p = inv.get(ch)
            short = DESC.get(f.type, {}).get(p) if p else None
            desc = (f.tdef.get("desc", {}).get(p) if p else None) or short
            notes = []
            if f.locked:
                notes.append("gesperrt - immer 0" + (" (nur ueber den Nebel-Knopf)" if f.manual_ok else ""))
            elif p in f.locked_params:
                notes.append("Laser: nur in der Szene Laser freigegeben" if p in f.laser_params else "gesperrt - immer 0")
            elif p in f.limits:
                notes.append("Grenze %d bis %d" % f.limits[p])
            if p in f.dead:
                notes.append("LED defekt")
            chans.append({"ch": ch, "dmx": f.address + ch - 1, "param": p or "", "short": short or p or "",
                          "desc": desc or p or "(nicht belegt)", "note": ", ".join(notes)})
        try:
            import fixture_edit as _fe
            allowed = _fe.allowed_groups(f.type, f.tdef)
        except Exception:                                  # noqa: BLE001
            allowed = [f.group]
        out.append({"nr": f.extra.get("nr", ""), "name": f.name, "label": f.extra.get("label", f.name), "type": f.type,
                    "group": f.group, "address": f.address, "end": f.address + f.n - 1, "n": f.n,
                    "target": f.target or rig.target, "own_target": f.extra.get("target", ""), "locked": f.locked,
                    "allowed": allowed, "user_added": bool(f.extra.get("user_added")), "channels": chans,
                    "hw_strobe": bool(f.tdef.get("hw_strobe")) and not f.locked, "blitz_ok": f.blitz_ok})
    if nano:                                          # alle Panels als ein Eintrag mit 3 Kanaelen je Panel
        chans = []
        for i, f in enumerate(nano):
            for j, (k, label) in enumerate((("r", "Rot"), ("g", "Gruen"), ("b", "Blau"))):
                chans.append({"ch": 3 * i + j + 1, "dmx": 3 * i + j + 1,
                              "desc": f"Panel {f.extra.get('nano_id', i)} {label}", "note": ""})
        out.append({"nr": 19, "name": "nanoleaf", "label": f"Nanoleaf Light Panels ({len(nano)} Panels)",
                    "type": "nanoleaf_panel", "group": "nano", "address": 1, "end": 3 * len(nano),
                    "target": nano[0].target, "locked": False, "channels": chans,
                    "nano_host": rig.nano["host"], "nano_file_host": rig.nano_file_host or "",
                    "nano_user_host": (rig.user or {}).get("nano_host", ""),
                    "nano_token_set": bool(rig.nano.get("token")),
                    "nano_token_changed": bool(getattr(rig, "nano_token_changed", False))})
    return out


def fixture_catalog(rig):
    """Katalog fuer den Fixture-Editor: Typen, Gruppen, ausgeblendete Fixtures, naechste freie Adresse, Neustart noetig?"""
    import fixture_edit as fe
    if rig.user is None:
        return {"editable": False}
    future = fe.apply_user(rig.base_cfg, rig.user)
    removed = [{"name": e["name"], "label": e.get("label", e["name"]), "nr": e.get("nr", ""), "address": e["address"]}
               for e in rig.base_cfg["fixtures"] if e["name"] in set(rig.user.get("removed", []))]
    return {"editable": True, "types": fe.type_summary(future), "groups": fe.GROUP_LABELS, "removed": removed,
            "next_nr": max([int(e.get("nr", 0) or 0) for e in future["fixtures"]] + [0]) + 1,
            "addresses": {t["name"]: fe.next_free_address(future, t["channels"]) for t in fe.type_summary(future)},
            "warning": rig.user_warning, "has_changes": bool(any(rig.user.get(k) for k in ("edits", "added", "removed", "types", "desc", "nano_host")))}


def dmx_values(rig, names):
    """Aktuelle Ausgabewerte (nach den Sicherheitsgrenzen) der gewuenschten Fixtures."""
    bufs = rig.render_all()
    res = {}
    for f in rig.fixtures:
        if f.name in names:
            b = bufs[f.target or rig.target]
            res[f.name] = list(b[f.address - 1:f.address - 1 + f.n])
    if "nanoleaf" in names:
        nano = [f for f in rig.fixtures if f.group == "nano"]
        if nano:
            b = bufs[nano[0].target]
            res["nanoleaf"] = list(b[:3 * len(nano)])
    return res


def _run(cmd, timeout=2.0):
    """Befehl ausfuehren; leerer Text, wenn er fehlt oder scheitert."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def net_status(sysroot="/sys/class/net", run=_run):
    """LAN- und WLAN-Anbindung des Raspberry: verbunden?, IP, Kabelgeschwindigkeit, WLAN-Name, Signal, Band.

    Liest /sys/class/net und die Befehle ip und iw (beides auf Raspberry Pi OS vorhanden). Fehlt etwas,
    bleibt das betreffende Feld einfach leer."""
    def rd(path):
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            return ""
    out = []
    try:
        names = sorted(os.listdir(sysroot))
    except OSError:
        return out
    default_if = ""
    for line in run(["ip", "route", "show", "default"]).splitlines():          # kleinste Metrik = Hauptverbindung
        parts = line.split()
        if "dev" in parts:
            m = int(parts[parts.index("metric") + 1]) if "metric" in parts else 0
            if not default_if or m < default_metric:
                default_if, default_metric = parts[parts.index("dev") + 1], m
    for name in names:
        base = os.path.join(sysroot, name)
        wireless = os.path.isdir(os.path.join(base, "wireless")) or name.startswith("wl")
        wired = (name.startswith(("eth", "en")) and not wireless)
        if not (wireless or wired):
            continue
        ip = ""
        for line in run(["ip", "-4", "-o", "addr", "show", "dev", name]).splitlines():
            parts = line.split()
            if "inet" in parts:
                ip = parts[parts.index("inet") + 1].split("/")[0]
                break
        state = rd(os.path.join(base, "operstate"))
        item = {"type": "WLAN" if wireless else "LAN", "name": name, "present": True,
                "up": bool(ip) and state in ("up", "unknown"), "ip": ip, "main": name == default_if,
                "speed": None, "ssid": "", "signal": None, "band": ""}
        if wired:
            sp = rd(os.path.join(base, "speed"))
            item["speed"] = int(sp) if sp.lstrip("-").isdigit() and int(sp) > 0 else None
        else:
            link = run(["iw", "dev", name, "link"])
            if link and "Not connected" not in link:
                for ln in link.splitlines():
                    ln = ln.strip()
                    if ln.startswith("SSID:"):
                        item["ssid"] = ln[5:].strip()
                    elif ln.startswith("signal:"):
                        try:
                            item["signal"] = int(float(ln.split()[1]))
                        except (ValueError, IndexError):
                            pass
                    elif ln.startswith("freq:"):
                        try:
                            f = float(ln.split()[1])
                            item["band"] = "5 GHz" if f >= 4900 else "2,4 GHz"
                        except (ValueError, IndexError):
                            pass
            if not item["ssid"]:
                item["ssid"] = run(["iwgetid", "-r", name]).strip()
        out.append(item)
    out.sort(key=lambda n: (n["type"] != "LAN", n["name"]))                  # LAN zuerst, dann WLAN
    return out


def _watch_net(show, every=5.0):
    while True:
        try:
            show.net = net_status()
        except Exception:                                # die Anzeige darf nie etwas stoeren
            pass
        time.sleep(every)


def ping_cmd(ip, platform=None):
    """Ein Ping mit 1 s Wartezeit. Windows schreibt die Optionen anders (-n Anzahl, -w Millisekunden), macOS -W in Millisekunden."""
    if (platform or sys.platform) == "win32":
        return ["ping", "-n", "1", "-w", "1000", ip]
    if (platform or sys.platform) == "darwin":                 # macOS: -W in Millisekunden (bisher 1 ms, nie eine Antwort)
        return ["ping", "-c", "1", "-W", "1000", ip]
    return ["ping", "-c", "1", "-W", "1", ip]


def _reachable(ip, port):
    """Ping; wenn der nicht durchkommt, ein TCP-Versuch (verweigerte Verbindung heisst: Geraet antwortet)."""
    try:
        if subprocess.run(ping_cmd(ip), capture_output=True, timeout=3).returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        socket.create_connection((ip, port), timeout=1.0).close()
        return True
    except ConnectionRefusedError:
        return True
    except OSError:
        return False


def config_url(name, ip):
    """Konfigurationsseite eines Geraets (Link im Bereich Verbindungen). Nanoleaf hat keine Weboberflaeche."""
    if name == "Art-Net-Gateway":
        return f"http://{ip}:9090/"                         # OLA-Weboberflaeche
    if name in ("Effektband", "Couchtisch", "Theke", "CCU"):
        return f"http://{ip}/"                              # WLED bzw. WebUI der HomeMatic-CCU
    return None


def _watch_hosts(show, every=5.0):
    names = {"effektband": "Effektband", "couchtisch": "Couchtisch", "theke": "Theke"}
    hosts = [("Art-Net-Gateway", show.rig.target, 9090)]
    hosts += [(names[n], fx.target, 80) for n in names for fx in show.rig.fixtures if fx.name == n and fx.target]
    if getattr(show.rig, "nano", None):
        hosts.append(("Nanoleaf", show.rig.nano["host"], int(show.rig.nano.get("port", 16021))))
    if getattr(show, "home", None) is not None:              # HomeMatic-CCU (Bereich Haus)
        hosts.append(("CCU", show.home.ccu["host"], int(show.home.ccu["ports"].get("HmIP-RF", 2010))))
    show.reach = {n: None for n, _, _ in hosts}
    show.reach_ip = {n: ip for n, ip, _ in hosts}
    show.reach_url = {n: url for n, url in ((n, config_url(n, ip)) for n, ip, _ in hosts) if url}
    while True:
        res = {}
        usb = show.dmx_usb_status() if hasattr(show, "dmx_usb_status") else None
        cfg = getattr(show, "cfg", None)
        have = lambda k: cfg is None or cfg[k + "_have"] > 0.5   # Geraet nicht vorhanden (14.11.2026): nicht pruefen, nicht melden
        for n, ip, port in hosts:
            if n == "Art-Net-Gateway" and (usb is not None or not have("ola")):   # DMX ueber den USB-Adapter: der OLA-Pi wird nicht gebraucht
                continue
            if (n in names.values() and not have("wled")) or (n == "Nanoleaf" and not have("nano")):
                continue
            res[n] = _reachable(ip, port)
        if usb is not None and have("ola"):
            res["DMX-USB"] = bool(usb["ok"])
            show.reach_ip["DMX-USB"] = usb["port"] or "USB"
        show.reach = res
        time.sleep(every)


# Betrieb ohne Mixxx (Wunsch 14.11.2026): in jede HTML-Seite, bevor sie aufgebaut wird; nomixxx.js blendet aus und ersetzt Texte
MX_OFF_HEAD = (b"<head><script>document.documentElement.classList.add('nomixxx')</script>"
               b"<link rel=\"stylesheet\" href=\"/static/sm/nomixxx.css\"><script src=\"/static/sm/nomixxx.js\" defer></script>")


def start(show, port):
    html = make_page().encode("utf-8")
    fixtures_page_html = fixtures_page().encode("utf-8")
    settings_page_html = settings_page().encode("utf-8")
    apc_page_html = apc_page().encode("utf-8")
    lumi_page_html = lumi_page().encode("utf-8")
    stats_page_html = stats_page().encode("utf-8")
    pre_page_html = pre_page().encode("utf-8")
    health_page_html = health_page().encode("utf-8")
    try:
        with open(FONT_FILE, "rb") as f:
            font_bytes = f.read()
    except OSError:
        font_bytes = b""                                     # ohne Datei nimmt der Browser die Systemschrift
    threading.Thread(target=_watch_hosts, args=(show,), daemon=True).start()
    threading.Thread(target=_watch_net, args=(show,), daemon=True).start()
    hl = health.Health(show, _run)
    from showman.api import ShowManager, handle_get as sm_get, handle_post as sm_post
    sm = ShowManager(show)                                   # Showmanager: Seiten /shows und /shows/edit
    threading.Thread(target=sm.watch_mixxx, daemon=True).start()
    threading.Thread(target=health.watch, args=(hl,), daemon=True).start()
    threading.Thread(target=hl.stall.run, name="haenger-spuerhund", daemon=True).start()

    class H(BaseHTTPRequestHandler):
        def handle_one_request(self):
            """Wie immer, dazu die Dauer je Anfrage fuer die Seite Zustand (Fehlersuche Haenger)."""
            t0 = time.perf_counter()
            self._op = ""
            super().handle_one_request()
            path = (getattr(self, "path", "") or "").split("?")[0]
            if path and not path.endswith("/ws"):                      # der WebSocket bleibt offen, das ist keine langsame Anfrage
                hl.reqs.note(path + (" " + self._op if self._op else ""), time.perf_counter() - t0, time.monotonic())

        def _send(self, code, body, ctype, extra=None):
            if (ctype.startswith("text/html") and show.cfg["mixxx_on"] < 0.5 and b"<head>" in body[:400]
                    and not self.path.startswith("/help")):      # das Handbuch bleibt vollstaendig
                body = body.replace(b"<head>", MX_OFF_HEAD, 1)   # Betrieb ohne Mixxx (Einstellung mixxx_on, 14.11.2026): jede Seite weiss es
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if "Cache-Control" not in (extra or {}):
                self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/musik/vorab" or self.path.startswith("/musik/vorab?"):   # Vorab-Laeufe (Datenpflege, 12.11.2026)
                self._send(200, pre_page_html, "text/html; charset=utf-8")
                return
            if sm_get(self, sm):
                return
            if self.path in ("/", "/index.html"):
                self._send(200, html, "text/html; charset=utf-8")
            elif self.path == "/static/inter.woff2":                          # Schrift Inter (liegt auf dem Pi, kein Internet noetig)
                if font_bytes:
                    self._send(200, font_bytes, "font/woff2", {"Cache-Control": "max-age=604800"})
                else:
                    self._send(404, b"", "text/plain")
            elif self.path == "/stats" or self.path.startswith("/stats?"):   # Statistik (runder Knopf neben dem Zahnrad)
                self._send(200, stats_page_html, "text/html; charset=utf-8")
            elif self.path == "/health" or self.path.startswith("/health?"):  # Zustand (Herz neben dem Statistik-Knopf)
                self._send(200, health_page_html, "text/html; charset=utf-8")
            elif self.path == "/api/health":
                self._send(200, json.dumps(hl.info(), ensure_ascii=False).encode(), "application/json")
            elif self.path == "/api/stats":
                self._send(200, json.dumps(show.stats_info(), ensure_ascii=False).encode(), "application/json")
            elif self.path == "/apc":                                          # APC mini als Grafik
                self._send(200, apc_page_html, "text/html; charset=utf-8")
            elif self.path == "/api/apc":
                import apc_view
                self._send(200, json.dumps(apc_view.state(show)).encode(), "application/json")
            elif self.path == "/lumi":                                         # ROLI Lumi als Grafik
                self._send(200, lumi_page_html, "text/html; charset=utf-8")
            elif self.path == "/lumi/LightButler.littlefoot":                  # Programm fuer den Lumi, aus der aktuellen Belegung
                import lumi_program
                import lumi_view
                self._send(200, lumi_program.program(lumi_view.controller(show).map["keys"]).encode(), "text/plain; charset=utf-8")
            elif self.path == "/api/lumi":
                import lumi_view
                self._send(200, json.dumps(lumi_view.state(show)).encode(), "application/json")
            elif self.path == "/settings" or self.path.startswith("/settings?"):   # Einstellungen auf eigener Seite
                self._send(200, settings_page_html, "text/html; charset=utf-8")
            elif self.path == "/fixtures" or self.path.startswith("/fixtures?"):   # Fixtures auf eigener Seite
                self._send(200, fixtures_page_html, "text/html; charset=utf-8")
            elif self.path == "/dmx" or self.path.startswith("/dmx?"):     # DMX-Monitor (alle 512 Kanaele, nur Anzeige)
                q = parse_qs(urlparse(self.path).query)
                lang = (q.get("lang") or ["en" if show.cfg["ui_lang"] > 0.5 else "de"])[0]
                self._send(200, dmx_page(lang).encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/dmx" or self.path.startswith("/api/dmx?"):
                q = parse_qs(urlparse(self.path).query)
                self._send(200, json.dumps(dmx_state(show, (q.get("t") or [None])[0])).encode(), "application/json")
            elif self.path == "/api/state":
                self._send(200, json.dumps(show.snapshot()).encode(), "application/json")
            elif self.path.startswith("/backup/"):
                p = backup_file(self.path[len("/backup/"):])
                if p is None:
                    self._send(404, b"nicht gefunden", "text/plain")
                else:
                    with open(p, "rb") as f:
                        data = f.read()
                    self._send(200, data, "application/zip",
                               {"Content-Disposition": f'attachment; filename="{os.path.basename(p)}"'})
            elif self.path == "/help/anlage":                                 # eigene Seite "Meine Anlage" (MEINE_ANLAGE.md)
                lang = "en" if show.cfg["ui_lang"] > 0.5 else "de"
                self._send(200, help_page(lang, anlage=True).encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/help/technik" or self.path.startswith("/help/technik?"):   # Technische Beschreibung
                q = parse_qs(urlparse(self.path).query)
                lang = (q.get("lang") or ["en" if show.cfg["ui_lang"] > 0.5 else "de"])[0]
                self._send(200, help_page("en" if lang == "en" else "de", technik=True).encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/help" or self.path.startswith("/help?"):   # Handbuch in der Sprache des Panels (?lang=de|en)
                q = parse_qs(urlparse(self.path).query)
                lang = (q.get("lang") or ["en" if show.cfg["ui_lang"] > 0.5 else "de"])[0]
                self._send(200, help_page("en" if lang == "en" else "de").encode("utf-8"), "text/html; charset=utf-8")
            elif self.path in ICONS:
                ic = icon_file(self.path)
                if ic is None:
                    self._send(204, b"", "image/x-icon")
                else:
                    self._send(200, ic[0], ic[1])
            elif self.path == "/api/backups":
                try:
                    import backup
                    cfg = backup.load_conf()
                    body = {"items": backup.list_backups(cfg)[:10], "dir": cfg["dir"], "keep": cfg["keep"],
                            "copy_to": cfg.get("copy_to", ""), "info": show.backup_info}
                except Exception as e:                           # noqa: BLE001
                    body = {"items": [], "error": str(e)[:120], "info": show.backup_info}
                self._send(200, json.dumps(body).encode(), "application/json")
            elif self.path == "/api/midi":
                mc, lc = getattr(show, "midi", None), getattr(show, "lumi", None)
                body = mc.status() if mc else {"none": True}
                if lc:
                    body["lumi"] = lc.status()
                self._send(200, json.dumps(body).encode(), "application/json")
            elif self.path == "/api/audio":
                fn = getattr(show.src, "audio_info", None)
                info = fn() if fn else {"sim": True}
                rec = getattr(show, "recorder", None)
                if rec is not None:
                    info["rec"] = rec.status()                 # Debug-Aufnahme (12.11.2026)
                self._send(200, json.dumps(info).encode(), "application/json")
            elif self.path == "/api/audio/level":
                fn = getattr(show.src, "level", None)
                lv = fn() if fn else {"sim": True}
                rec = getattr(show, "recorder", None)
                if rec is not None:
                    lv["rec"] = {"on": rec.on, "rec": rec.wav is not None, "cur_s": round(rec.cur_n / rec.rate, 1), "dropped": rec.dropped}
                self._send(200, json.dumps(lv).encode(), "application/json")
            elif self.path.startswith("/aufnahmen/"):           # Debug-Aufnahme herunterladen (nur Dateien aus dem Ordner)
                rec = getattr(show, "recorder", None)
                p = rec.path_of(unquote(self.path[len("/aufnahmen/"):])) if rec is not None else None
                if not p:
                    self._send(404, b"nicht gefunden", "text/plain")
                else:
                    with open(p, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg" if p.endswith(".mp3") else "audio/wav")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Content-Disposition", 'attachment; filename="' + os.path.basename(p) + '"')
                    self.end_headers()
                    self.wfile.write(data)
            elif self.path == "/api/scenes":
                self._send(200, json.dumps(show.scenes_info()).encode(), "application/json")
            elif self.path == "/api/genres":                                  # Genre-Stile: Tabelle fuers Panel
                seen = list(show.mixxx.genres) if show.mixxx is not None and hasattr(show.mixxx, "genres") else []
                seen += [[g, n] for g, n in list(show.live_genres.items())]  # auch die von der Titelerkennung gefundenen
                self._send(200, json.dumps({"rows": show.gstyles.table(seen)}, ensure_ascii=False).encode(), "application/json")
            elif self.path == "/api/about":                                    # Seite Ueber Light-Butler (static/sm/about.html)
                self._send(200, json.dumps(about_info(show), ensure_ascii=False).encode(), "application/json")
            elif self.path == "/LICENSE":                                      # Lizenztext GPLv3 (Seite Ueber)
                txt = next((open(p, "rb").read() for p in LICENSE_FILES if os.path.isfile(p)), b"LICENSE fehlt")
                self._send(200, txt, "text/plain; charset=utf-8")
            elif self.path == "/about":                                        # Seite Ueber Light-Butler
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "sm", "about.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif self.path == "/api/nav":                                      # Kopfleiste aller Unterseiten (static/sm/nav.js)
                self._send(200, json.dumps(nav_info(show), ensure_ascii=False).encode(), "application/json")
            elif self.path == "/api/texts":
                t = show.texts
                self._send(200, json.dumps({"rev": t.rev, "texts": t.merged(), "table": t.table()}, ensure_ascii=False).encode(),
                           "application/json")
            elif self.path == "/api/settings":
                self._send(200, json.dumps(show.cfg.info()).encode(), "application/json")
            elif self.path == "/api/fixtures":
                self._send(200, json.dumps(fixtures_info(show.rig)).encode(), "application/json")
            elif self.path == "/api/fxcat":
                self._send(200, json.dumps(fixture_catalog(show.rig)).encode(), "application/json")
            elif self.path.split("?")[0] == "/fixtures.yaml":
                try:
                    import fixture_edit as fe
                    text = fe.export_yaml(fe.apply_user(show.rig.base_cfg, show.rig.user))
                except Exception as e:                           # noqa: BLE001
                    self._send(500, ("Export nicht moeglich: %s" % e).encode(), "text/plain; charset=utf-8")
                    return
                self._send(200, text.encode("utf-8"), "text/yaml; charset=utf-8",
                           {"Content-Disposition": 'attachment; filename="fixtures.yaml"'})
            elif self.path.startswith("/api/dmx"):
                q = parse_qs(urlparse(self.path).query)
                names = set(",".join(q.get("names", [])).split(","))
                self._send(200, json.dumps(dmx_values(show.rig, names)).encode(), "application/json")
            else:
                self._send(404, b"nicht gefunden", "text/plain")

        def do_POST(self):
            if sm_post(self, sm):
                return
            if self.path != "/api/cmd":
                self._send(404, b"nicht gefunden", "text/plain")
                return
            try:
                n = int(self.headers.get("Content-Length", "0"))
                d = json.loads(self.rfile.read(n) or b"{}")
                show.command(d)
                self._send(200, json.dumps(show.snapshot()).encode(), "application/json")
            except (ValueError, KeyError, TypeError) as e:
                self._send(400, json.dumps({"error": str(e)}).encode(), "application/json")

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Web-Panel: http://<IP-dieses-Rechners>:{port}/  (nur im Heimnetz benutzen, keine Anmeldung)", flush=True)
    return srv
