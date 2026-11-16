// core.js - Showmanager: Datenmodell und Bearbeitung (ohne Oberflaeche, mit node testbar), Serverzugriff, Synchronisation.
(function (root) {
  'use strict';
  const SM = {};

  // ---- Hilfen -------------------------------------------------------------------------------------
  let idn = 0;
  SM.uid = p => (p || 'x') + Date.now().toString(36) + (idn++).toString(36) + Math.random().toString(36).slice(2, 5);
  SM.clone = o => JSON.parse(JSON.stringify(o));
  // Gibt es das Lied schon als MP3? (Wunsch 08.11.2026: WAV/MP4 nur bemaengeln, wenn dasselbe Lied nicht auch als MP3 da ist.)
  // Gleich = gleicher Ordner und Dateiname ohne Endung, oder gleicher Interpret und Titel (ohne Gross/klein und Satzzeichen).
  // tracks wie /api/musik (path, artist, name); Rueckgabe: Funktion r -> true, wenn r eine MP3 ist oder eine MP3-Schwester hat.
  SM.mp3Twin = tracks => {
    const nk = s => String(s || '').normalize('NFC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
    const pk = p => String(p || '').normalize('NFC').toLowerCase().replace(/\.[^./]+$/, '');
    const isMp3 = r => /\.mp3$/i.test(r.path || '');
    const dir = p => pk(p).replace(/\/[^/]*$/, '');
    const keys = new Set();
    for (const r of tracks || []) if (r.path && isMp3(r)) {
      keys.add('p:' + pk(r.path));
      if (nk(r.artist) && nk(r.name)) keys.add('t:' + nk(r.artist) + '|' + nk(r.name));
      if (nk(r.name)) keys.add('d:' + dir(r.path) + '|' + nk(r.name));     // gleicher Ordner, gleicher Titel (WAV oft ohne Interpret)
    }
    return r => isMp3(r) || keys.has('p:' + pk(r.path)) || (!!nk(r.artist) && !!nk(r.name) && keys.has('t:' + nk(r.artist) + '|' + nk(r.name))) ||
      (!!nk(r.name) && keys.has('d:' + dir(r.path) + '|' + nk(r.name)));
  };
  // Kann die Datei ein eigenes Cover tragen? (MP3 mit ID3, MP4/M4A/AAC; WAV, AIFF, FLAC zeigt der Mac nicht, 09.11.2026)
  SM.canCover = p => /\.(mp3|mp4|m4a|aac)$/i.test(String(p || ''));
  SM.clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  // Betrieb ohne Mixxx (Einstellung "Mixxx verwenden" aus, 14.11.2026): der Pi setzt die Klasse nomixxx (nomixxx.js blendet aus)
  SM.MXOFF = typeof document !== 'undefined' && document.documentElement.classList.contains('nomixxx');
  SM.esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  SM.fmtTime = t => {
    t = Math.max(0, t || 0);
    const m = Math.floor(t / 60), s = t - m * 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(3);
  };
  SM.parseTime = text => {
    const p = String(text).trim().replace(',', '.').split(':');
    if (!p.length || p.length > 3 || p.some(x => x === '' || isNaN(+x))) return null;
    return p.reduce((a, x) => a * 60 + +x, 0);
  };
  SM.hex2 = v => Math.round(SM.clamp(v, 0, 255)).toString(16).padStart(2, '0');
  SM.colorToHex = c => '#' + SM.hex2(c[0]) + SM.hex2(c[1]) + SM.hex2(c[2]);
  SM.hexToColor = (h, w, uv) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16), w || 0, uv || 0];

  SM.kindOf = attr => attr === 'color' ? 'color' : attr === 'move' ? 'move' : attr === 'laser' ? 'laser' : attr === 'fog' ? 'fog' : attr === 'nano_fx' ? 'nano_fx' : attr === 'panel_scene' ? 'panel' : 'scalar';
  SM.clipsOnly = attr => attr === 'laser' || attr === 'fog' || attr === 'nano_fx' || attr === 'panel_scene';     // keine Keyframes
  SM.defaultValue = kind => kind === 'color' ? [255, 255, 255, 0, 0] : kind === 'move' ? [0.5, 0.5] : 255;
  SM.EASES = [['linear', 'Linear'], ['ease_in', 'Ease In'], ['ease_out', 'Ease Out'], ['ease_in_out', 'Ease In/Out'], ['constant', 'Konstant']];
  SM.ease = (e, u) => e === 'linear' ? u : e === 'constant' ? 0 : e === 'ease_in' ? u * u : e === 'ease_out' ? 1 - (1 - u) * (1 - u) : u * u * (3 - 2 * u);

  // Anzeige der Abspielposition: Manche Browser liefern currentTime nur grob, dann ruckelt die Linie hinter dem Ton her.
  // Zwischen zwei neuen Werten läuft die Anzeige selbst weiter, nie rückwärts und höchstens 0,25 s ohne neuen Wert.
  SM.SmoothClock = class {
    constructor() { this.last = null; this.base = 0; this.baseT = 0; this.out = 0; }
    update(ct, nowMs, playing) {
      if (!playing || this.last === null || Math.abs(ct - this.out) > 0.5) {   // Stillstand oder Sprung: genau der Wert
        this.last = ct; this.base = ct; this.baseT = nowMs; this.out = ct;
        return ct;
      }
      if (ct !== this.last) { this.last = ct; this.base = ct; this.baseT = nowMs; }
      const est = this.base + Math.min(0.25, (nowMs - this.baseT) / 1000);
      this.out = Math.max(this.out, est);
      return this.out;
    }
  };
  // Anzeige vorziehen, in ms, je Browser gemerkt: nur die Linie im Bild, nie das Licht oder gesetzte Zeiten
  SM.displayLead = () => { try { return SM.clamp(+localStorage.getItem('smlead') || 0, -500, 500); } catch (e) { return 0; } };
  SM.setDisplayLead = ms => { try { localStorage.setItem('smlead', String(ms)); } catch (e) { /* privates Fenster */ } };

  // Loop im Editor: springt zurück, sobald die Position das Ende überschreitet. Wer dahinter springt, spielt normal weiter.
  SM.loopJump = (prev, pos, loop) => (loop && loop.on && prev !== null && prev < loop.t1 && pos >= loop.t1 ? loop.t0 : null);
  // Bereich aus den gewählten Ereignissen, sonst null
  SM.loopFromSelection = (doc, ids) => {
    const items = [...ids].map(id => SM.find(doc, id)).filter(Boolean);
    if (!items.length) return null;
    const t0 = Math.min(...items.map(x => x.ev.t)), t1 = Math.max(...items.map(x => x.ev.t + (x.ev.d || 0)));
    return t1 > t0 ? { t0, t1 } : null;
  };

  // ---- Raster --------------------------------------------------------------------------------------
  SM.GRIDS = [['off', 'Aus'], ['bar', 'Takt'], ['beat', 'Beat'], ['half', '1/2 Beat'], ['quarter', '1/4 Beat'], ['sec', '1 s'], ['tenth', '0,1 s']];
  SM.gridStep = (doc, grid) => {
    const beat = 60 / (doc.bpm || 120);
    return { bar: beat * (doc.beats_per_bar || 4), beat, half: beat / 2, quarter: beat / 4, sec: 1, tenth: 0.1 }[grid] || 0;
  };
  SM.snap = (t, doc, grid) => {
    const st = SM.gridStep(doc, grid);
    if (!st) return Math.max(0, t);
    const off = (grid === 'sec' || grid === 'tenth') ? 0 : (doc.beat_offset || 0);
    return Math.max(0, Math.round((t - off) / st) * st + off);
  };

  // Linien im Raster: minor und major in Sekunden, null = keine. Zu eng gezeichnet wird es nicht: dann nur jede n-te Linie.
  SM.gridLines = (doc, grid, pxs) => {
    const st = SM.gridStep(doc, grid);
    if (!st) return null;
    const music = grid !== 'sec' && grid !== 'tenth';
    let minor = st, major = music ? SM.gridStep(doc, 'bar') : (grid === 'sec' ? 10 : 1);
    const k = Math.ceil(5 / (minor * pxs));
    if (k > 1) {
      const base = [1, 2, 4, 5, 8, 10, 16, 20, 32, 40, 64, 80, 100, 128, 256, 512, 1024].find(n => n >= k) || 2048;
      minor *= base;
      if (major < minor * 2) major = minor * 4;
    }
    return { minor, major, off: music ? (doc.beat_offset || 0) : 0 };
  };

  // Form eines Musters ueber einen Zyklus (0..1), fuer die Vorschau im Clip
  SM.shapeAt = (key, x, p) => {
    const duty = p && p.duty !== undefined ? p.duty : 0.5;
    switch (key) {
      case 'fade_in': return x;
      case 'fade_out': return 1 - x;
      case 'blink': case 'strobe': return x < duty ? 1 : 0;
      case 'pulse': return Math.exp(-5 * x);
      case 'beat': return Math.exp(-6 * x);
      case 'chase': return x < 0.35 ? 1 : 0;
      case 'running': return 1 - x;
      default: return 0.5 - 0.5 * Math.cos(2 * Math.PI * x);    // Sinus, Gruppenwelle
    }
  };
  SM.clipCycles = (c, doc) => {
    const p = c.p || {};
    if (p.repeat > 0) return p.repeat;
    if (c.pattern === 'fade_in' || c.pattern === 'fade_out') return 1;
    if (c.pattern === 'beat') return c.d * (doc.bpm || 120) / 60 * (p.speed || 1);
    if (p.beat_sync) return c.d * (doc.bpm || 120) / 60 * (p.speed || 1);
    return c.d * (p.speed || 1);
  };

  // Rand eines Blocks unter der Maus: 'l', 'r' oder '' (Mitte). Auch ein kurzer Block behält eine Mitte zum Verschieben.
  SM.clipEdge = (x, a, b) => {
    const zone = Math.min(10, (b - a) / 3);
    if (x >= b - zone && x <= b + SM.EDGE_OUT) return 'r';
    if (x <= a + zone && x >= a - SM.EDGE_OUT) return 'l';
    return '';
  };
  SM.EDGE_OUT = 5;                                               // auch knapp außerhalb trifft den Rand
  // Treffer in einer Liste von Blöcken: zuerst genau darin (der oberste), sonst knapp daneben am Rand
  SM.hitClip = (list, x, xOf) => {
    let near = null;
    for (let i = list.length - 1; i >= 0; i--) {
      const c = list[i], a = xOf(c.t), b = xOf(c.t + c.d);
      if (x >= a && x <= b) return { ev: c, edge: SM.clipEdge(x, a, b) };
      if (!near && x >= a - SM.EDGE_OUT && x <= b + SM.EDGE_OUT) near = { ev: c, edge: SM.clipEdge(x, a, b) };
    }
    return near;
  };
  // Schritt der Pfeilchen an den Zeitfeldern: das Raster, ohne Raster 0,1 s
  SM.timeStep = doc => SM.gridStep(doc, doc.grid) || 0.1;

  // ---- Suchen --------------------------------------------------------------------------------------
  SM.find = (doc, id) => {
    for (const c of doc.scene_clips) if (c.id === id) return { type: 'scene', ev: c, list: doc.scene_clips };
    for (const tr of doc.tracks) {
      for (const k of tr.keys) if (k.id === id) return { type: 'key', ev: k, track: tr, list: tr.keys };
      for (const c of tr.clips) if (c.id === id) return { type: 'clip', ev: c, track: tr, list: tr.clips };
    }
    return null;
  };
  SM.targetKey = tg => tg.master ? 'master' : tg.panel ? 'panel' : tg.group ? 'g:' + tg.group : 'f:' + tg.fixture;
  SM.isMaster = tr => !!tr.target.master;
  // Ende einer Liedzeile, wie line_end in showman/lyrics.py
  SM.lyricEnd = (L, i) => {
    const guess = L[i][0] + Math.min(12, 2 + 0.6 * String(L[i][1]).split(/\s+/).filter(Boolean).length);
    return i + 1 < L.length ? Math.min(guess, L[i + 1][0]) : guess;
  };
  SM.isPinned = tr => !!(tr.target.master || tr.target.panel);   // stehen fest oben und scrollen nicht mit
  SM.panelTrack = doc => {
    let tr = doc.tracks.find(t => t.target.panel);
    if (!tr) { tr = { id: 'panel', target: { panel: true }, attr: 'panel_scene', mute: false, keys: [], clips: [] }; doc.tracks.unshift(tr); }
    return tr;
  };
  SM.masterTrack = doc => {                     // Master-Zeile: liegt bei den Spuren, die Timeline zeigt sie fest oben
    let tr = doc.tracks.find(SM.isMaster);
    if (!tr) { tr = { id: 'master', target: { master: true }, attr: 'master', mute: false, keys: [], clips: [] }; doc.tracks.unshift(tr); }
    return tr;
  };
  SM.findTrack = (doc, target, attr) => doc.tracks.find(t => SM.targetKey(t.target) === SM.targetKey(target) && t.attr === attr);
  SM.ensureTrack = (doc, target, attr) => {
    let tr = SM.findTrack(doc, target, attr);
    if (!tr) {
      tr = { id: SM.uid('t'), target: target.group ? { group: target.group } : { fixture: target.fixture }, attr, mute: false, keys: [], clips: [] };
      const key = SM.targetKey(target);
      let at = -1;
      doc.tracks.forEach((t, i) => { if (SM.targetKey(t.target) === key) at = i; });
      if (at >= 0) doc.tracks.splice(at + 1, 0, tr); else doc.tracks.push(tr);
    }
    return tr;
  };

  // Alle Spuren eines Geräts vor die Spuren eines anderen legen (beforeKey null = ans Ende). True, wenn sich etwas geändert hat.
  SM.moveTarget = (doc, key, beforeKey) => {
    if (key === beforeKey) return false;
    const mine = doc.tracks.filter(t => SM.targetKey(t.target) === key);
    const rest = doc.tracks.filter(t => SM.targetKey(t.target) !== key);
    if (!mine.length) return false;
    let at = beforeKey === null ? rest.length : rest.findIndex(t => SM.targetKey(t.target) === beforeKey);
    if (at < 0) at = rest.length;
    const next = rest.slice(0, at).concat(mine, rest.slice(at));
    if (next.every((t, i) => t === doc.tracks[i])) return false;
    doc.tracks = next;
    return true;
  };
  // Wo tut eine Spur etwas? Für die Mini-Spuren eingeklappter Geräte: Zeitbereiche der Clips und der Keyframes.
  SM.trackSpans = tr => {
    const out = tr.clips.map(c => ({ t0: c.t, t1: c.t + c.d, clip: c }));
    if (tr.keys.length) out.unshift({ t0: tr.keys[0].t, t1: tr.keys[tr.keys.length - 1].t, keys: tr.keys });
    return out;
  };

  // ---- Bearbeiten: reine Funktionen auf der Show ------------------------------------------------------
  SM.addKey = (doc, track, t, v, e) => {
    const k = { id: SM.uid('k'), t: Math.max(0, t), v, e: e || 'linear' };
    track.keys.push(k);
    track.keys.sort((a, b) => a.t - b.t);
    return k;
  };
  SM.addClip = (track, t, d, pattern, p, label) => {
    const c = { id: SM.uid('c'), t: Math.max(0, t), d: Math.max(0.025, d), pattern, p: p ? SM.clone(p) : {}, label: label || '' };
    track.clips.push(c);
    track.clips.sort((a, b) => a.t - b.t);
    return c;
  };
  SM.addSceneClip = (doc, t, d, scene) => {
    const c = { id: SM.uid('sc'), t: Math.max(0, t), d: Math.max(0.025, d), scene, fade_in: 0, fade_out: 0 };
    doc.scene_clips.push(c);
    return c;
  };
  SM.resort = doc => {
    doc.scene_clips.sort((a, b) => a.t - b.t);
    for (const t of doc.tracks) {
      t.keys.sort((a, b) => a.t - b.t);
      t.clips.sort((a, b) => a.t - b.t);
    }
  };
  // Verschiebt alle Ereignisse um dt; niemand rutscht vor den Anfang (die Gruppe bleibt zusammen).
  SM.moveEvents = (doc, ids, dt) => {
    const items = [...ids].map(id => SM.find(doc, id)).filter(Boolean);
    const first = Math.min(...items.map(x => x.ev.t));
    const d = Math.max(dt, -first);
    for (const x of items) x.ev.t += d;
    SM.resort(doc);
    return d;
  };
  SM.deleteEvents = (doc, ids) => {
    for (const id of ids) {
      const x = SM.find(doc, id);
      if (x) x.list.splice(x.list.indexOf(x.ev), 1);
    }
  };
  SM.copyEvents = (doc, ids) => {
    const items = [...ids].map(id => SM.find(doc, id)).filter(Boolean);
    if (!items.length) return null;
    const base = Math.min(...items.map(x => x.ev.t));
    return { base, items: items.map(x => ({ type: x.type, track: x.track ? x.track.id : null, ev: SM.clone(x.ev) })) };
  };
  SM.pasteEvents = (doc, clip, t) => {
    const ids = [];
    for (const it of clip.items) {
      const ev = SM.clone(it.ev);
      ev.t = Math.max(0, it.ev.t - clip.base + t);
      ev.id = SM.uid(it.type === 'key' ? 'k' : it.type === 'clip' ? 'c' : 'sc');
      if (it.type === 'scene') doc.scene_clips.push(ev);
      else {
        const tr = doc.tracks.find(x => x.id === it.track);
        if (!tr) continue;
        (it.type === 'key' ? tr.keys : tr.clips).push(ev);
      }
      ids.push(ev.id);
    }
    SM.resort(doc);
    return ids;
  };
  SM.keyValueAt = (track, t) => {
    const K = track.keys;
    if (!K.length) return null;
    if (t <= K[0].t) return K[0].v;
    const L = K[K.length - 1];
    if (t >= L.t) return L.v;
    let i = 0;
    while (i < K.length - 1 && K[i + 1].t <= t) i++;
    const a = K[i], b = K[i + 1], u = SM.ease(a.e, (t - a.t) / (b.t - a.t));
    if (typeof a.v === 'number') return a.v + (b.v - a.v) * u;
    return a.v.map((x, j) => x + (b.v[j] - x) * u);
  };

  // ---- Undo und Redo: ganze Staende, einfach und sicher ------------------------------------------------
  SM.History = class {
    constructor(limit) { this.limit = limit || 200; this.undoS = []; this.redoS = []; }
    push(doc) {
      const s = JSON.stringify(doc);
      if (this.undoS[this.undoS.length - 1] === s) return;
      this.undoS.push(s);
      if (this.undoS.length > this.limit) this.undoS.shift();
      this.redoS.length = 0;
    }
    undo(doc) {
      if (!this.undoS.length) return null;
      this.redoS.push(JSON.stringify(doc));
      return JSON.parse(this.undoS.pop());
    }
    redo(doc) {
      if (!this.redoS.length) return null;
      this.undoS.push(JSON.stringify(doc));
      return JSON.parse(this.redoS.pop());
    }
  };

  // ---- Server --------------------------------------------------------------------------------------
  SM.get = async url => {
    const r = await fetch(url, { cache: 'no-store' });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || r.statusText);
    return d;
  };
  // Gerade geloeschte Dateien (Musik-Datenbank, Doppelte): 30 Minuten ausblenden, auch wenn die Liste vom Pi sie noch kurz
  // meldet, bis die Bruecke die neue Fassung geschickt hat (Fehlerbericht 07.11.2026: geloeschte Lieder tauchten wieder auf)
  const GONE_KEY = 's2l_geloescht', GONE_MS = 30 * 60 * 1000;
  const goneLoad = () => { try { return JSON.parse(localStorage.getItem(GONE_KEY) || '{}') || {}; } catch (e) { return {}; } };
  SM.goneMark = path => {
    const g = goneLoad(), now = Date.now();
    for (const k of Object.keys(g)) if (now - g[k] > GONE_MS) delete g[k];
    g[path] = now;
    try { localStorage.setItem(GONE_KEY, JSON.stringify(g)); } catch (e) { /* privates Fenster: nur diese Sitzung */ }
  };
  SM.goneSet = () => { const g = goneLoad(), now = Date.now(); return new Set(Object.keys(g).filter(k => now - g[k] <= GONE_MS)); };
  SM.cmd = async (op, data) => {
    const r = await fetch('/api/sm/cmd', { method: 'POST', body: JSON.stringify(Object.assign({ op }, data || {})) });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || r.statusText);
    return d;
  };
  // Eigene Rueckfrage statt confirm()/prompt() des Browsers: Safari am iPad bietet an, weitere Dialoge einer Seite zu
  // blockieren, danach antwortet der Browser still mit Abbrechen und nichts passiert (Fehlerbericht 06.11.2026: Show liess
  // sich nicht loeschen). SM.ask(text, wert) -> Text oder null; ohne wert (undefined) nur Ja/Nein -> true/false.
  SM.ask = (text, value, okLabel) => new Promise(res => {
    const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const m = document.createElement('div');
    m.className = 'modal';
    m.style.zIndex = 1000;                                 // immer ganz oben: lag hinter dem Fade-Fenster (z 80), nur der dunkle Hintergrund war zu sehen (Fehlerbericht 11.11.2026)
    const input = value !== undefined;
    m.innerHTML = '<div class="box"><p style="white-space:pre-line;margin:0 0 10px">' + esc(text) + '</p>' +
      (input ? '<div class="row"><input id="smaskv" style="flex:1" value="' + esc(value) + '"></div>' : '') +
      '<div class="row"><button id="smaskok" class="on">' + esc(okLabel || 'OK') + '</button><button id="smaskno">Abbrechen</button></div></div>';
    document.body.appendChild(m);
    const i = m.querySelector('#smaskv');
    const done = v => { m.remove(); res(v); };
    m.querySelector('#smaskok').onclick = () => done(input ? i.value : true);
    m.querySelector('#smaskno').onclick = () => done(input ? null : false);
    m.onkeydown = e => { if (e.key === 'Escape') done(input ? null : false); if (e.key === 'Enter' && input) done(i.value); };
    if (i) { i.focus(); i.select(); } else m.querySelector('#smaskok').focus();
  });
  SM.toast = (text, ms) => {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = text;
    el.style.display = 'block';
    clearTimeout(SM._toast);
    SM._toast = setTimeout(() => { el.style.display = 'none'; }, ms || 3000);
  };

  // Audio analysieren: der Browser dekodiert, damit der Pi kein ffmpeg braucht und Handys nicht jedes Mal dekodieren muessen.
  SM.analyzeBuffer = buf => {
    const ch = buf.numberOfChannels, n = buf.length, sr = buf.sampleRate;
    const data = [];
    for (let i = 0; i < ch; i++) data.push(buf.getChannelData(i));
    const PEAK_HZ = 50, ENV_HZ = 100;
    const pstep = sr / PEAK_HZ, estep = sr / ENV_HZ;
    const mins = [], maxs = [], env = [];
    let lp = 0, sum = 0, cnt = 0, mn = 1, mx = -1, np = pstep, ne = estep;
    const a = 1 - Math.exp(-2 * Math.PI * 180 / sr);        // Tiefpass: der Kick gibt den Takt vor
    for (let i = 0; i < n; i++) {
      let x = 0;
      for (let c = 0; c < ch; c++) x += data[c][i];
      x /= ch;
      if (x < mn) mn = x;
      if (x > mx) mx = x;
      lp += a * (x - lp);
      sum += lp * lp;
      cnt++;
      if (i >= np) {
        mins.push(Math.round(mn * 127));
        maxs.push(Math.round(mx * 127));
        mn = 1; mx = -1; np += pstep;
      }
      if (i >= ne) {
        env.push(Math.round(Math.sqrt(sum / cnt) * 1000) / 1000);
        sum = 0; cnt = 0; ne += estep;
      }
    }
    return { duration: buf.duration, peaks: { rate: PEAK_HZ, min: mins, max: maxs }, env, envRate: ENV_HZ };
  };

  // ---- Verbindung zum Pi: Audio-Position hin, Stand zurueck ------------------------------------------------
  SM.clientId = () => {
    try {
      let id = sessionStorage.getItem('smc');
      if (!id) { id = SM.uid('b'); sessionStorage.setItem('smc', id); }
      return id;
    } catch (e) { return SM._cid || (SM._cid = SM.uid('b')); }
  };

  SM.Link = class {
    // report(): {pos, playing} oder null, wenn dieser Browser keine Musik spielt. onStatus(st): Stand vom Pi.
    constructor(report, onStatus) {
      this.report = report; this.onStatus = onStatus;
      this.rtt = 40; this.ws = null; this.fails = 0; this.watch = null; this.client = SM.clientId();
      this.connect();
      setInterval(() => this.tick(), 200);
    }
    connect() {
      let ws;
      try { ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/api/sm/ws'); } catch (e) { this.fails++; return; }
      this.ws = ws;
      ws.onopen = () => { this.fails = 0; this.setWatch(this.watch); };
      ws.onmessage = m => {
        const d = JSON.parse(m.data);
        if (d.t === 'pong') {
          const r = performance.now() - d.ts;
          this.rtt = r < this.rtt ? r : this.rtt * 0.9 + r * 0.1;      // das schnellste Paket liegt am naechsten an der echten Laufzeit
        } else if (d.t === 'st') this.onStatus(d);
      };
      ws.onclose = () => { this.ws = null; this.fails++; setTimeout(() => this.connect(), Math.min(5000, 500 * this.fails)); };
      ws.onerror = () => { try { ws.close(); } catch (e) { /* schon zu */ } };
    }
    setWatch(name) {
      this.watch = name;
      if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ t: 'watch', fixture: name }));
    }
    async tick() {
      const r = this.report();
      const open = this.ws && this.ws.readyState === 1;
      if (r) {
        const msg = { t: 'sync', client: this.client, pos: r.pos, playing: r.playing, rtt: this.rtt, ol: SM.outputLatency(), ts: performance.now() };
        if (open) this.ws.send(JSON.stringify(msg));
        else if (this.fails > 2) { try { this.onStatus(await SM.cmd('report', msg)); } catch (e) { /* Light-Butler nicht erreichbar */ } }
      } else if (!open && this.fails > 2 && (this.pollN = (this.pollN || 0) + 1) % 5 === 0) {
        try { this.onStatus(await SM.get('/api/sm/status')); } catch (e) { /* Light-Butler nicht erreichbar */ }
      }
    }
  };
  // ---- Quick: Show zu einem Lied der Mixxx-Bibliothek anlegen und vom Assistenten fuellen lassen ------------------------
  // Musik-Datenbank und Hauptpanel (Wunsch von Markus). song = {path, title, dur, artist, name}, music = Vorhoer-Server am
  // Mac, state(text) zeigt den Schritt. Rueckgabe: Name der Show. Bei Fehlern kommt die halbe Show in den Papierkorb.
  SM.showName = r => (r.artist ? r.artist + ' - ' + r.name : (r.name || r.title || 'Show')).replace(/[^\p{L}\p{N} .()_\-]/gu, ' ').replace(/\s+/g, ' ').trim().replace(/^[^\p{L}\p{N}]+/u, '').slice(0, 60).replace(/[. ]+$/, '');
  // Regler "Ruhig bis wild" nach der Energiestufe des Liedes vorstellen (Wunsch von Markus): 1 ganz ruhig, 6 Mitte, 9 fast ganz wild,
  // ohne Stufe die Mitte. Gleicher Wert im Fenster des Assistenten und bei Quick.
  SM.wildFor = lvl => { lvl = +lvl || 0; if (!lvl) return 0.5; return Math.round(Math.max(0.05, Math.min(0.9, 0.5 + (lvl - 6) * 0.12)) * 20) / 20; };
  SM.quickShow = async (song, music, state) => {
    const say = state || (() => {});
    const name = SM.showName(song);
    let created = false;
    try {
      say('⚙ lege an …');
      await SM.cmd('create', { name, title: song.title, dur: song.dur });
      created = true;
      say('⚙ MP3 vom Musik-Rechner …');
      const resp = await fetch(music + '/audio?p=' + encodeURIComponent(song.path));
      if (!resp.ok) throw new Error('Die MP3 kommt nicht vom Musik-Rechner (' + resp.status + ')');
      const blob = await resp.blob();
      say('⚙ MP3 zum Light-Butler …');
      const up = await fetch('/api/sm/audio?name=' + encodeURIComponent(name), { method: 'POST', body: blob });
      const uj = await up.json().catch(() => ({}));
      if (!up.ok || uj.error) throw new Error(uj.error || 'Hochladen fehlgeschlagen (' + up.status + ')');
      say('⚙ Wellenform …');
      const C = window.AudioContext || window.webkitAudioContext;
      const ac = new C();
      const buf = await ac.decodeAudioData(await blob.arrayBuffer());
      if (ac.close) ac.close();
      const a = SM.analyzeBuffer(buf);
      await SM.cmd('peaks', { name, data: a.peaks });
      const t = (await SM.cmd('analyze', { env: a.env, rate: a.envRate })).tempo || {};
      await SM.cmd('quick_meta', { name, duration: a.duration, bpm: t.bpm, offset: t.offset });
      say('⚙ Cues, Liedtext …');
      try { await SM.cmd('marks_from_mac', { name }); } catch (e) { /* ohne Cues: aus der Wellenform */ }
      try { await SM.cmd('lyrics_quick', { name }); } catch (e) { /* ohne Liedtext */ }
      say('⚙ Assistent …');
      const info = await SM.cmd('assist_info', { name });
      await SM.cmd('assist', { name, style: info.style || '', wild: SM.wildFor(info.lvl), laser: true, fog: true, strobe: true, move: true,
        ambient: false, nano_fx: true, claude: false, design: false, keep_copy: false });
      return name;
    } catch (e) {
      if (created) await SM.cmd('delete', { name }).catch(() => {});
      throw e;
    }
  };

  // ---- Cover groß zeigen: Maus darüber (am Tablet lange drücken zeigt der Browser selbst) ---------------------------
  // Abspiel-Leiste unten fuer jede Seite mit Vorhoeren (Wunsch 09.11.2026: "auf jeder Seite gleich"): Play/Pause, Position im
  // Lied zum Springen, Zeit, Lautstaerke (gemeinsam mit Musik-DB und Datei-Seiten, localStorage musikvol), Schliessen.
  // bar = SM.playBar(audio); bar.show('Titel') nach audio.src/play(); bar.hide().
  // Stick auswerfen (Wunsch 10.11.2026): der Mac haelt die Hintergrundarbeiten an und wirft den Musik-Stick aus
  // (music_serve /eject, stick_hold.py). say(text, art) zeigt den Stand; art 'ok' | 'err' | ''.
  // Stand der Liedliste (Wunsch 11.11.2026: aus der Musik-Datenbank in die Datenpflege): was der Mac tut (music_serve /status)
  // und wie viel der Pi schon hat (/api/musik: connected, complete, prog). Gibt HTML zurueck.
  SM.libStatusHtml = (d, st) => {
    const out = [], mins = s => s < 60 ? 'unter einer Minute' : Math.round(s / 60) + ' min';
    const mini = (a, b) => '<span class="mini"><i style="width:' + (b ? Math.min(100, 100 * a / b) : 0) + '%"></i></span>';
    if (d) {
      const n = (d.tracks || []).length;
      out.push(!n ? (d.connected ? 'Die Mixxx-Brücke schickt die Bibliothek gerade …' : 'Noch keine Bibliothek am Light-Butler: am Musik-Rechner den Helfer oder die App „Light-Butler Mixxx“ starten.')
        : !d.connected ? 'Musik-Rechner nicht verbunden: Liste aus der Ablage am Light-Butler (Stand vom letzten Mal), ' + n + ' Lieder.'
        : !d.complete ? '<span class="bsy">Liste aus der Ablage am Light-Butler, der Musik-Rechner schickt gerade die aktuelle Bibliothek.</span>' : '✓ Der Light-Butler hat die aktuelle Liste: ' + n + ' Lieder.');
      const p = Array.isArray(d.prog) ? d.prog : null;
      if (!d.complete && d.connected && p && p[1] > 0)
        out.push('Light-Butler hat empfangen: ' + mini(p[0], p[1]) + p[0] + ' von ' + p[1] + ' Teilen (' + Math.floor(100 * p[0] / p[1]) + ' %)' + (p[2] ? ', ' + (p[1] - p[0]) + ' gingen im WLAN verloren, der Musik-Rechner schickt sie nach' : ''));
    }
    const t = st && st.tags;
    if (t) out.push(t.busy ? (t.total ? '<span class="bsy">Musik-Rechner liest die Tags der MP3s:</span> ' + mini(t.done, t.total) + t.done + ' von ' + t.total + ' Dateien'
      : '<span class="bsy">Musik-Rechner sucht die MP3s auf dem Stick …</span>')
      : t.ago >= 0 ? 'Musik-Rechner: Tags aus ' + t.files + ' MP3s gelesen vor ' + mins(t.ago) + ', nächster Durchgang in ' + mins(t.next) : 'Musik-Rechner: Tags der MP3s noch nicht gelesen');
    const s = st && st.send;
    const what = s && s.kind === 'geaenderte' ? ' (nur Geänderte)' : s && s.kind === 'fehlende' ? ' (nur verlorene)' : '';
    if (s && s.n) out.push(s.busy ? '<span class="bsy">Musik-Rechner schickt die Liste an den Light-Butler' + what + ':</span> ' + mini(s.sent, s.n) + 'Teil ' + s.sent + ' von ' + s.n
      : s.same ? 'Musik-Rechner: Der Light-Butler hat die aktuelle Liste, nichts zu schicken (nächste Prüfung in ' + mins(s.next) + ')'
      : 'Musik-Rechner: zuletzt geschickt ' + s.n + ' Teile' + what + ', nächste Prüfung in ' + mins(s.next));
    return out.join('<br>');
  };

  // Fade-in/-out als Sammelauftrag (Wunsch 11.11.2026): der Mac bearbeitet die MP3s eine nach der anderen (audio_fade.py).
  // paths: Pfade der Bibliothek; fin/fout/ca/cb vorbelegt (Wellenform im Tag-Fenster) oder im Fenster eingegeben.
  // ca/cb = vorne/hinten abschneiden (11.11.2026), im selben Durchgang wie der Fade.
  SM.fadeDlg = (music, paths, label, opt) => {
    opt = opt || {};
    const esc = SM.esc;
    if (!music) { SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer oder die Mixxx-App?).', 5000); return; }
    const mp3 = paths.filter(p => /\.mp3$/i.test(p));
    if (!mp3.length) { SM.toast('Keine MP3s in der Auswahl.', 4000); return; }
    const m = document.createElement('div');
    m.className = 'modal';
    m.style.zIndex = 80;                                   // ueber der Wellenform (70)
    m.innerHTML = '<div class="box"><h2>Fade und Schnitt' + (label ? ' „' + esc(label) + '“' : '') + ': ' + mp3.length + ' MP3' + (mp3.length === paths.length ? '' : ' (von ' + paths.length + ' Liedern)') + '</h2>' +
      '<p class="dim" style="margin:-4px 0 8px">Am Anfang von 0 auf 100 %, am Ende von 100 auf 0 %. Der Musik-Rechner kodiert den Ton neu (320 kbit/s), Tags und Cover bleiben gleich, das Original kommt in den Papierkorb. 0 = kein Fade. „vorne weg“ und „hinten weg“ schneiden zuerst ab, der Fade gilt dann für das, was bleibt (alles in einem Durchgang).</p>' +
      '<div class="row"><label>Fade-in <input type="number" id="fdin" min="0" max="60" step="0.5" value="' + (opt.fin != null ? opt.fin : 0) + '" style="width:5em"> s</label>' +
      '<label>Fade-out <input type="number" id="fdout" min="0" max="60" step="0.5" value="' + (opt.fout != null ? opt.fout : 5) + '" style="width:5em"> s</label></div>' +
      '<div class="row"><label>vorne weg <input type="number" id="fdca" min="0" max="600" step="0.5" value="' + (opt.ca || 0) + '" style="width:5em"> s</label>' +
      '<label>hinten weg <input type="number" id="fdcb" min="0" max="600" step="0.5" value="' + (opt.cb || 0) + '" style="width:5em"> s</label></div>' +
      '<div id="fdmsg" class="dim" style="min-height:1.3em"></div><div id="fdbar" style="height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin:8px 0" hidden><i style="display:block;height:100%;background:var(--acc);width:0"></i></div>' +
      '<div class="row"><button id="fdgo" class="on">Starten</button><button id="fdstop" hidden>Anhalten</button><button id="fdclose">Schließen</button></div></div>';
    document.body.appendChild(m);
    const q = s => m.querySelector(s);
    let poll = null;
    const close = () => { clearInterval(poll); m.remove(); };
    q('#fdclose').onclick = close;
    const show = s => {
      const run = s.state === 'run';
      q('#fdbar').hidden = false; q('#fdbar i').style.width = (s.total ? 100 * (s.done || 0) / s.total : 0) + '%';
      q('#fdmsg').textContent = run ? 'Bearbeite ' + ((s.done || 0) + 1) + ' von ' + s.total + (s.cur ? ': ' + s.cur : '') + ' …'
        : s.state === 'ok' ? 'Fertig: ' + (s.ok || 0) + ' bearbeitet' + ((s.errors || []).length ? ', ' + s.errors.length + ' nicht: ' + s.errors.slice(0, 3).join('; ') : '') + '.'
        : s.state === 'stopped' ? 'Angehalten nach ' + (s.done || 0) + ' von ' + s.total + '.' : '';
      q('#fdstop').hidden = !run; q('#fdgo').disabled = run;
      if (!run) { clearInterval(poll); if (s.state === 'ok' && opt.done) opt.done(s); }
    };
    q('#fdstop').onclick = () => fetch(music + '/fade', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'stop' }) });
    q('#fdgo').onclick = async () => {
      const fin = +q('#fdin').value || 0, fout = +q('#fdout').value || 0, ca = +q('#fdca').value || 0, cb = +q('#fdcb').value || 0;
      if (!fin && !fout && !ca && !cb) { q('#fdmsg').textContent = 'Fade oder Schnitt wählen.'; return; }
      const cutTxt = (ca ? ', vorne ' + ca + ' s weg' : '') + (cb ? ', hinten ' + cb + ' s weg' : '');
      if (!opt.autostart && !await SM.ask(mp3.length + ' MP3' + (mp3.length > 1 ? 's' : '') + ': Fade-in ' + fin + ' s, Fade-out ' + fout + ' s' + cutTxt + '.' + (ca ? '\n\nVorne abschneiden verschiebt Hotcues und Beat-Raster in Mixxx.' : '') + '\n\nDie Originale kommen in den Papierkorb. Starten?', undefined, 'Starten')) return;
      opt.autostart = false;
      try {
        const r = await fetch(music + '/fade', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'start', paths: mp3, fin, fout, ca, cb }) });
        const d = await r.json(); if (d.error) throw new Error(d.error);
        show(d);
        poll = setInterval(async () => { try { show(await (await fetch(music + '/fade')).json()); } catch (e) { /* kurz weg */ } }, 1000);
      } catch (e) { q('#fdmsg').textContent = 'Fade: ' + e.message; }
    };
    if (opt.autostart) q('#fdgo').click();
  };

  // Lautheit angleichen (Wunsch 11.11.2026): Ziel -14 LUFS wie bei Spotify. lufs/tp aus der Messung am Mac (loudness.py).
  // boost false: nur leiser machen (Vorhoeren ueber audio.volume); true: auch lauter, aber nur bis 1 dB unter der Spitze (Auto-DJ, WebAudio).
  SM.LOUD_TARGET = -14;
  SM.loudDb = (lufs, tp, boost) => {
    if (!lufs) return 0;
    let g = SM.LOUD_TARGET - lufs;
    if (g > 0) g = boost ? Math.min(g, 9, Math.max(0, -1 - (tp || 0))) : 0;
    return Math.round(g * 10) / 10;
  };
  SM.dbFactor = db => Math.pow(10, (db || 0) / 20);

  // drive (Seite Spiegeln, 12.11.2026): {path, name, music} eines anderen Laufwerks, etwa des Ersatzsticks; ohne = Musik-Stick.
  // Interpreten (13.11.2026): Hauptname und Schluessel wie pi/showman/artists.py (main_name, key); tests/test_interpreten.py vergleicht
  SM.artistMain = a => String(a || '').normalize('NFC').trim()
    .replace(/\s*;.*$|\s+(?:feat\.?|ft\.?|featuring|vs\.?|versus)\s+.*$|\s*\((?:feat\.?|ft\.?|featuring)\s.*\)\s*$/i, '').trim().replace(/^[ ,-]+|[ ,-]+$/g, '');
  SM.artistKey = a => {
    const s = SM.artistMain(a).toLowerCase().replace(/ß/g, 'ss').normalize('NFKD').replace(/\p{M}/gu, '');
    let k = s.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80).replace(/-+$/, '');
    if (!k && s.trim()) k = ('u-' + [...s.trim()].filter(c => !/\s/.test(c)).map(c => c.codePointAt(0).toString(16)).join('-').slice(0, 70)).replace(/-+$/, '');
    return k;
  };

  // Auswahl mit Haekchen hinter einem Knopf (Wunsch 13.11.2026, Genre-Filter auf den Seiten Interpreten und Alben).
  // p = SM.checkPicker(knopf, {name: 'Genre', key: 'localStorage-Schluessel', onChange}); p.render([{title, items: [{v, t, n}]}]);
  // p.sel = gewaehlte Werte (leer = alle). Die Auswahl merkt sich der Browser.
  SM.checkPicker = (btn, opt) => {
    if (!document.getElementById('s2lcpk')) {
      const st = document.createElement('style'); st.id = 's2lcpk';
      st.textContent = '.cpkw{position:relative;display:inline-block}.cpk{position:absolute;z-index:30;top:40px;left:0;width:min(420px,92vw);max-height:60vh;overflow:auto;' +
        'background:var(--pan,#1f2230);border:1px solid var(--line,#333);border-radius:10px;padding:8px 10px;box-shadow:0 10px 30px #000a}' +
        '.cpk .ah{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}.cpk .ah button{min-height:28px;font-size:12.5px;padding:2px 8px}' +
        '.cpk .ag{color:var(--dim,#999);font-size:12px;margin:8px 0 2px}.cpk label{display:flex;gap:8px;align-items:center;padding:3px 0;font-size:13.5px}' +
        '.cpk label .n{margin-left:auto;color:var(--dim,#999);font-variant-numeric:tabular-nums}';
      document.head.appendChild(st);
    }
    const esc = SM.esc, w = document.createElement('span');
    w.className = 'cpkw';
    btn.parentNode.insertBefore(w, btn);
    w.appendChild(btn);
    const pan = document.createElement('div');
    pan.className = 'cpk'; pan.hidden = true;
    pan.innerHTML = '<div class="ah"><button data-x="all">Alle anhaken</button><button data-x="none">Keine (= alle zeigen)</button><button data-x="close">Fertig</button></div><div class="cl"></div>';
    w.appendChild(pan);
    const list = pan.querySelector('.cl');
    const me = { sel: [] };
    try { const v = JSON.parse(localStorage.getItem(opt.key) || 'null'); if (Array.isArray(v)) me.sel = v.filter(x => typeof x === 'string'); } catch (e) { /* privates Fenster */ }
    const save = () => { try { localStorage.setItem(opt.key, JSON.stringify(me.sel)); } catch (e) { /* egal */ } };
    const label = () => {
      const n = me.sel.length;
      btn.textContent = opt.name + ': ' + (!n ? 'alle' : n <= 2 ? me.sel.join(', ') : me.sel[0] + ' + ' + (n - 1) + ' weitere') + ' ▾';
      btn.classList.toggle('on', n > 0);
    };
    let known = null;
    me.render = groups => {
      known = new Set(groups.flatMap(g => g.items.map(i => i.v)));
      if (known.size) me.sel = me.sel.filter(v => known.has(v));     // Werte, die es nicht mehr gibt, fallen weg
      const h = groups.filter(g => g.items.length).map(g => (g.title ? '<div class="ag">' + esc(g.title) + '</div>' : '') +
        g.items.map(i => '<label><input type="checkbox" value="' + esc(i.v) + '"' + (me.sel.includes(i.v) ? ' checked' : '') + '> ' + esc(i.t) + '<span class="n">' + i.n + '</span></label>').join('')).join('') ||
        '<div class="dim">Nichts zur Auswahl.</div>';
      if (list.dataset.h !== h) { list.innerHTML = h; list.dataset.h = h; }
      label();
    };
    const changed = () => { save(); label(); if (opt.onChange) opt.onChange(me.sel); };
    btn.addEventListener('click', () => { pan.hidden = !pan.hidden; });
    pan.addEventListener('click', e => {
      const b = e.target.closest('button[data-x]'); if (!b) return;
      if (b.dataset.x === 'close') { pan.hidden = true; return; }
      me.sel = b.dataset.x === 'all' ? [...list.querySelectorAll('input')].map(i => i.value) : [];
      list.querySelectorAll('input').forEach(i => { i.checked = me.sel.includes(i.value); });
      changed();
    });
    list.addEventListener('change', () => { me.sel = [...list.querySelectorAll('input:checked')].map(i => i.value); changed(); });
    document.addEventListener('click', e => { if (!pan.hidden && !w.contains(e.target)) pan.hidden = true; });
    label();
    return me;
  };

  SM.ejectStick = async (music, say, drive) => {
    say = say || (t => SM.toast(t, 6000));
    if (!music) { say('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer oder die Mixxx-App?).', 'err'); return false; }
    const other = drive && !drive.music;
    if (!await SM.ask(other ? '„' + drive.name + '“ am Musik-Rechner auswerfen?\n\nIst noch ein Programm darauf (Finder-Fenster, Mixxx), sagt der Light-Butler, welches.'
      : 'Den Musik-Stick am Musik-Rechner auswerfen?\n\nDer Light-Butler hält dafür seine Arbeit am Stick an (Tags lesen, Prüfen, Schätzen …). Läuft Mixxx mit einem Lied aus dem Stick, zuerst Mixxx beenden.', undefined, 'Auswerfen')) return false;
    try {
      const r = await fetch(music + '/eject', drive ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ vol: drive.path }) } : { method: 'POST' });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
    } catch (e) { say('Auswerfen: ' + e.message, 'err'); return false; }
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 1000));
      let s = null;
      try { s = await (await fetch(music + '/eject')).json(); } catch (e) { continue; }
      if (s.state === 'wait') say('Halte die Arbeit am Stick an …' + (s.open ? ' (' + s.open + ' Datei' + (s.open === 1 ? '' : 'en') + ' noch offen)' : ''), '');
      else if (s.state === 'eject') say('Werfe aus …', '');
      else if (s.state === 'ok') { say(other ? '⏏ „' + drive.name + '“ ausgeworfen, du kannst ihn abziehen.' : '⏏ Stick ausgeworfen, du kannst ihn abziehen. Steckst du ihn wieder an, arbeitet der Light-Butler von selbst weiter.', 'ok'); return true; }
      else if (s.state === 'err') { say('⚠ ' + (s.error || 'Auswerfen ging nicht'), 'err'); return false; }
    }
    say('Auswerfen dauert ungewöhnlich lange. Im Finder nachsehen.', 'err');
    return false;
  };

  SM.playBar = (audio, opt) => {
    opt = opt || {};
    if (!document.getElementById('s2lplaycss')) {
      const st = document.createElement('style'); st.id = 's2lplaycss';
      st.textContent = '.s2lplay{position:fixed;left:0;right:0;bottom:0;display:none;align-items:center;gap:10px;padding:8px 14px;background:#1f2230;border-top:1px solid var(--line,#333);z-index:50;flex-wrap:wrap}' +
        '.s2lplay.on{display:flex}body.s2lplaying{padding-bottom:80px}.s2lplay .pt{flex:1 1 200px;min-width:120px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
        '.s2lplay .ppos{flex:3 1 240px;min-width:120px}.s2lplay .ptm{font-variant-numeric:tabular-nums;color:var(--dim,#999);font-size:12px;min-width:84px;text-align:right}' +
        '.s2lplay .pvol{display:flex;align-items:center;gap:4px;color:var(--dim,#999);font-size:13px}.s2lplay .pvol input{width:90px}' +
        '.s2lplay button{min-width:34px;min-height:30px;border-radius:6px}';
      document.head.appendChild(st);
    }
    const el = document.createElement('div'); el.className = 's2lplay';
    el.innerHTML = '<button class="ppp" title="Abspielen / Pause">▶</button><span class="pt"></span><input type="range" class="ppos" min="0" max="1000" value="0" title="Im Lied springen">' +
      '<span class="ptm"></span><span class="pvol" title="Lautstärke (gilt auf allen Seiten zum Vorhören)"><span class="pvi">🔊</span><input type="range" class="pv" min="0" max="100" value="80"></span><button class="pcl" title="Schließen">✕</button>';
    document.body.appendChild(el);
    const q = c => el.querySelector('.' + c);
    const tm = t => { t = Math.max(0, Math.round(t || 0)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); };
    const icon = v => v == 0 ? '🔇' : v < 50 ? '🔉' : '🔊';
    let vol = 80, seeking = false;
    try { vol = Math.max(0, Math.min(100, parseInt(localStorage.getItem('musikvol') || '80', 10) || 0)); } catch (e) { /* privates Fenster */ }
    q('pv').value = vol; audio.volume = vol / 100; q('pvi').textContent = icon(vol);
    q('pv').addEventListener('input', () => {
      audio.volume = q('pv').value / 100; q('pvi').textContent = icon(q('pv').value);
      try { localStorage.setItem('musikvol', q('pv').value); } catch (e) { /* privates Fenster */ }
    });
    const draw = () => {
      q('ppp').textContent = audio.paused ? '▶' : '❚❚';
      const d = audio.duration || 0;
      if (!seeking) q('ppos').value = d && isFinite(d) ? Math.round(1000 * audio.currentTime / d) : 0;
      q('ptm').textContent = tm(audio.currentTime) + ' / ' + tm(isFinite(d) ? d : 0);
    };
    ['timeupdate', 'play', 'pause', 'loadedmetadata', 'ended'].forEach(ev => audio.addEventListener(ev, draw));
    q('ppos').addEventListener('input', () => { seeking = true; const d = audio.duration || 0; q('ptm').textContent = tm(d * q('ppos').value / 1000) + ' / ' + tm(d); });
    q('ppos').addEventListener('change', () => { const d = audio.duration || 0; if (d && isFinite(d)) audio.currentTime = d * q('ppos').value / 1000; seeking = false; });
    q('ppp').onclick = () => { if (!audio.src) return; if (audio.paused) audio.play().catch(() => {}); else audio.pause(); };
    const bar = {
      el,
      show(title) { q('pt').textContent = title || ''; el.classList.add('on'); document.body.classList.add('s2lplaying'); draw(); },
      hide() { audio.pause(); el.classList.remove('on'); document.body.classList.remove('s2lplaying'); if (opt.onclose) opt.onclose(); },
    };
    q('pcl').onclick = bar.hide;
    if (opt.start !== false) bar.pv = SM.preview(audio, { pos: q('ppos'), after: q('ppp'), end: q('pcl') });   // ab Hauptteil (14.11.2026)
    return bar;
  };

  // ---- Vorhoeren ab der wichtigen Stelle (Wunsch 14.11.2026) ----
  // Beim Antippen von ▶ beginnt das Lied nicht ganz vorne, sondern: Beginn des ersten Hauptteils, sonst 2. Hotcue, sonst
  // erster Drop, sonst bei einem Drittel. Kurz eingeblendet. Die Marken holt der Pi (Ablage oder Musik-Rechner,
  // /api/sm/preview_marks); bis sie da sind, beginnt es beim Drittel und springt dann an die richtige Stelle, solange man
  // nicht selbst gesprungen ist. Im Schiebebalken Striche (gruen Hauptteil, orange Hotcue, rot Drop), ⏮ = Anfang,
  // ⏭ = naechste Stelle (sonst 30 s weiter), Haken "ab Hauptteil" (localStorage vorhoer_ab, Standard an).
  SM.pvMarks = new Map();
  SM.pvOn = () => { try { return localStorage.getItem('vorhoer_ab') !== '0'; } catch (e) { return true; } };
  SM.pvEntry = (m, du) => {
    m = m || {}; du = +du || 0;
    const ok = t => t >= 5 && (!du || t < du - 20);
    const main = (m.se || []).find(x => x[0] === 'main' && ok(x[1]));
    if (main) return { t: main[1], why: 'Hauptteil' };
    const cu = m.cu || [];
    if (cu.length > 1 && cu[1] > 0 && (!du || cu[1] < du - 20)) return { t: cu[1], why: '2. Hotcue' };
    const dr = (m.ev || []).find(x => x[0] === 'drop' && ok(x[1]));
    if (dr) return { t: dr[1], why: 'Drop' };
    return du > 60 ? { t: Math.round(du / 3), why: 'ein Drittel' } : { t: 0, why: '' };
  };
  SM.pvPoints = (m, du) => {
    m = m || {};
    const pts = [...(m.se || []).filter(x => x[0] === 'main').map(x => ({ t: x[1], k: 'main' })), ...(m.cu || []).map(t => ({ t, k: 'cue' })),
      ...(m.ev || []).filter(x => x[0] === 'drop').map(x => ({ t: x[1], k: 'drop' }))].filter(x => x.t > 0 && (!du || x.t < du)).sort((a, b) => a.t - b.t);
    return pts.filter((x, i) => !i || x.t - pts[i - 1].t > 2);
  };
  SM.preview = (audio, ui) => {
    if (!document.getElementById('s2lpvcss')) {
      const st = document.createElement('style'); st.id = 's2lpvcss';
      st.textContent = '.pvw{position:relative;display:inline-flex;align-items:center}.pvw>input{width:100%;box-sizing:border-box;margin-left:0;margin-right:0}' +
        '.pvw .pvt{position:absolute;bottom:-5px;width:3px;height:6px;margin-left:-1px;border-radius:1px;pointer-events:none}' +
        '.pvt.main{background:#8fe0a5}.pvt.cue{background:#ff9a3c}.pvt.drop{background:#ff5c5c}' +
        '.pvb{min-width:34px;min-height:30px;border-radius:6px}.pvab{display:inline-flex;align-items:center;gap:4px;color:var(--dim,#999);font-size:12px;white-space:nowrap}';
      document.head.appendChild(st);
    }
    const pos = ui.pos, cs = getComputedStyle(pos), w = document.createElement('span');
    w.className = 'pvw';
    w.style.flex = cs.flex; w.style.minWidth = cs.minWidth;
    if (cs.flexGrow === '0') w.style.width = cs.width;
    pos.parentNode.insertBefore(w, pos); w.appendChild(pos);
    const mk = h => { const t = document.createElement('template'); t.innerHTML = h; return t.content.firstChild; };
    const bS = mk('<button class="pvb" title="Vom Anfang des Liedes" aria-label="Vom Anfang">⏮</button>');
    const bN = mk('<button class="pvb" title="Zur nächsten Stelle (Hauptteil, Drop, Hotcue), sonst 30 Sekunden weiter" aria-label="Nächste Stelle">⏭</button>');
    const lab = mk('<label class="pvab" title="▶ beginnt beim Hauptteil, sonst beim 2. Hotcue, sonst beim ersten Drop, sonst bei einem Drittel (gilt auf allen Seiten zum Vorhören)"><input type="checkbox"> ab Hauptteil</label>');
    ui.after.after(bS, bN);
    ui.end.before(lab);
    const cb = lab.querySelector('input');
    cb.checked = SM.pvOn();
    cb.onchange = () => { try { localStorage.setItem('vorhoer_ab', cb.checked ? '1' : '0'); } catch (e) { /* privates Fenster */ } };
    let p = '', marks = null, user = false, prov = -1, fadeT = 0;
    const pathOf = () => { try { return new URL(audio.src, location.href).searchParams.get('p') || ''; } catch (e) { return ''; } };
    const du = () => (isFinite(audio.duration) && audio.duration) || 0;
    const ticks = () => {
      w.querySelectorAll('.pvt').forEach(x => x.remove());
      const d = du(); if (!d || !marks) return;
      const NM = { main: 'Hauptteil', cue: 'Hotcue', drop: 'Drop' };
      for (const x of SM.pvPoints(marks, d)) {
        const e = document.createElement('span'); e.className = 'pvt ' + x.k; e.title = NM[x.k]; e.style.left = (100 * x.t / d).toFixed(2) + '%'; w.appendChild(e);
      }
    };
    // Kurz einblenden (am iPad laesst Safari die Lautstaerke nicht aendern: dann ohne). Fehlerbericht 14.11.2026: kam ein
    // zweites Einblenden, bevor das erste fertig war (Marken kommen spaet, naechstes Lied), galt die halbe Lautstaerke als Ziel,
    // Lied fuer Lied leiser, beim dritten kein Ton mehr. Jetzt: Ziel bleibt die Lautstaerke vor dem ersten Einblenden;
    // aendert die Seite oder der Regler die Lautstaerke, endet das Einblenden sofort.
    let fadeTo = null, lastV = -1;                         // volumechange kommt spaeter: am Wert erkennen, ob wir es waren
    const setV = v => { audio.volume = v; lastV = audio.volume; };
    const stopFade = () => { clearInterval(fadeT); if (fadeTo !== null) { setV(fadeTo); fadeTo = null; } };
    audio.addEventListener('volumechange', () => { if (fadeTo !== null && Math.abs(audio.volume - lastV) > 0.001) { clearInterval(fadeT); fadeTo = null; } });
    const fade = () => {
      const v = fadeTo !== null ? fadeTo : audio.volume;
      clearInterval(fadeT); fadeTo = null;
      if (!v) return;
      fadeTo = v; setV(0);
      if (audio.volume) { fadeTo = null; return; }          // laesst sich nicht aendern (iPad)
      let i = 0;
      fadeT = setInterval(() => { i++; if (i >= 10) stopFade(); else setV(v * i / 10); }, 50);
    };
    const go = t => { audio.currentTime = t; fade(); };
    audio.addEventListener('loadstart', () => {
      const np = pathOf();
      if (np === p) return;
      p = np; user = false; prov = -1; marks = SM.pvMarks.get(p) || null; ticks();
      if (!p || marks) return;
      const want = p;
      fetch('/api/sm/preview_marks?p=' + encodeURIComponent(p)).then(r => r.json()).then(m => {
        SM.pvMarks.set(want, m || {});
        if (p !== want) return;
        marks = m || {}; ticks();
        const d = du();
        if (prov >= 0 && !user && cb.checked && d && Math.abs(audio.currentTime - prov) < 8) {
          const e = SM.pvEntry(marks, d);
          if (Math.abs(e.t - prov) > 1) go(e.t);
        }
      }).catch(() => { SM.pvMarks.set(want, {}); });
    });
    audio.addEventListener('loadedmetadata', () => {
      ticks();
      if (!cb.checked || user || audio.currentTime > 1) return;
      const e = SM.pvEntry(marks, du());
      if (!marks) prov = e.t;
      if (e.t > 0) go(e.t);
    });
    const mine = () => { user = true; };
    pos.addEventListener('input', mine); pos.addEventListener('change', mine);
    bS.onclick = () => { if (!audio.src) return; user = true; audio.currentTime = 0; if (audio.paused) audio.play().catch(() => {}); };
    bN.onclick = () => {
      if (!audio.src) return;
      user = true;
      const d = du(), t = audio.currentTime, nx = SM.pvPoints(marks, d).find(x => x.t > t + 2);
      const to = nx ? nx.t : t + 30;
      if (d && to >= d - 2) return;
      go(to);
      if (audio.paused) audio.play().catch(() => {});
    };
    return { ticks };
  };

  // Spotify-Suche (Wunsch 14.11.2026): fehlende Titel bei den Alben, leere Suche in der Musik-Datenbank. Eigenes Fenster
  // "lb_spotify" (jede weitere Suche kommt in dasselbe, der Light-Butler bleibt, wie er war); hin geht nur der Suchtext.
  SM.SPOTIFY_SEARCH = 'https://open.spotify.com/search/';
  SM.SPOTIFY_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" style="vertical-align:middle"><circle cx="12" cy="12" r="11" fill="#1ed760"/>' +
    '<path d="M6.5 9.3c3.8-1.1 8.1-.8 11.3 1.1M7.1 12.6c3.1-.9 6.6-.6 9.3 1M7.7 15.7c2.5-.7 5.1-.5 7.3.8" fill="none" stroke="#121212" stroke-width="1.7" stroke-linecap="round"/></svg>';
  SM.spotifyLink = (q, label, title) => '<a class="spot" href="' + SM.SPOTIFY_SEARCH + encodeURIComponent(String(q || '').trim()) + '" target="lb_spotify" rel="noopener" title="' +
    SM.esc(title || 'Auf Spotify suchen: ' + q) + '" aria-label="Auf Spotify suchen">' + SM.SPOTIFY_SVG + (label ? ' ' + SM.esc(label) : '') + '</a>';

  // Merkliste "Fehlt mir" (Wunsch 14.11.2026): Knopf neben dem Spotify-Symbol (fehlende Album-Titel, leere Suche in der
  // Musik-Datenbank). Gemerkt am Pi (showman/missing.py); was spaeter in die Sammlung kommt, zeigt die Liste nicht mehr.
  SM.missKeys = new Set();
  SM.missKey = e => { const n = s => String(s || '').toLowerCase().split(/\s+/).filter(Boolean).join(' ').slice(0, 200);
    return e.q ? 'q:' + n(e.q) : 't:' + n(e.a) + '|' + n(e.t); };
  SM.missLoad = () => fetch('/api/sm/missing').then(r => r.json()).then(d => { SM.missKeys = new Set(d.keys || []); SM.missDraw(); return d; }).catch(() => null);
  SM.missBtn = e => { const k = SM.missKey(e), on = SM.missKeys.has(k);
    return '<button class="missb' + (on ? ' on' : '') + '" data-mk="' + SM.esc(k) + '" data-me="' + SM.esc(JSON.stringify(e)) + '" title="' +
      (on ? 'Steht auf der Liste „Fehlt mir“ (antippen nimmt es wieder heraus)' : 'Auf die Liste „Fehlt mir“ setzen (Datenpflege → Fehlt mir)') + '">' + (on ? '✓ gemerkt' : '+ merken') + '</button>'; };
  SM.missDraw = () => document.querySelectorAll('.missb[data-mk]').forEach(b => {
    const on = SM.missKeys.has(b.dataset.mk); b.classList.toggle('on', on); b.textContent = on ? '✓ gemerkt' : '+ merken'; });
  if (typeof document !== 'undefined') document.addEventListener('click', async ev => {   // core.js laeuft auch unter node (Tests)
    const b = ev.target.closest && ev.target.closest('.missb[data-mk]'); if (!b) return;
    ev.preventDefault(); ev.stopPropagation();
    const k = b.dataset.mk, on = SM.missKeys.has(k);
    try {
      const d = on ? await SM.cmd('missing_del', { k }) : await SM.cmd('missing_add', JSON.parse(b.dataset.me || '{}'));
      SM.missKeys = new Set(d.keys || []); SM.missDraw();
      SM.toast(on ? 'Von der Liste „Fehlt mir“ genommen.' : 'Auf der Liste „Fehlt mir“ (Datenpflege → Fehlt mir).', 2500);
      document.dispatchEvent(new CustomEvent('s2lmiss', { detail: d }));
    } catch (e) { SM.toast('Merken: ' + e.message, 5000); }
  }, true);
  if (typeof document !== 'undefined' && !document.getElementById('s2lmisscss')) {
    const st = document.createElement('style'); st.id = 's2lmisscss';
    st.textContent = '.missb{min-height:24px;padding:1px 8px;font-size:11.5px;border-radius:12px;white-space:nowrap;margin-left:6px}.missb.on{color:#8fe0a5;border-color:#8fe0a5}';
    document.head.appendChild(st);
  }

  // Lauftext: zu lange Titel in .mq (Inhalt in einem span) gleiten hin und zurueck, kurze bleiben stehen (14.11.2026)
  SM.marquee = (root) => {
    const run = () => (root || document).querySelectorAll('.mq').forEach(el => {
      const sp = el.firstElementChild;
      if (!sp) return;
      el.classList.remove('run');
      const dx = sp.scrollWidth - el.clientWidth;
      if (dx > 2) {
        el.style.setProperty('--mqx', -dx + 'px');
        el.style.setProperty('--mqd', Math.max(3, dx / 22 + 2).toFixed(1) + 's');
        el.classList.add('run');
      }
    });
    requestAnimationFrame(run);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(run);
  };
  SM.coverZoom = () => {
    if (typeof document === 'undefined' || SM._cz) return;
    const z = document.createElement('img');
    z.alt = '';
    z.style.cssText = 'position:fixed;z-index:9999;width:300px;height:300px;object-fit:cover;border-radius:10px;box-shadow:0 10px 40px rgba(0,0,0,.6);pointer-events:none;display:none';
    SM._cz = z;
    const ok = el => el && el.tagName === 'IMG' && (el.classList.contains('cvimg') || el.id === 'pcover');
    document.addEventListener('pointerover', e => {
      if (e.pointerType !== 'mouse' || !ok(e.target)) return;
      if (!z.parentNode) document.body.appendChild(z);
      const r = e.target.getBoundingClientRect(), W = innerWidth, H = innerHeight;
      const S = Math.min(+(e.target.dataset.zoom || 300), W - 16, H - 16);   // data-zoom: groesser (Interpreten-Bild 500, 13.11.2026)
      z.src = e.target.src;
      z.style.width = z.style.height = S + 'px';
      z.style.left = Math.max(8, Math.min(W - S - 8, r.right + S + 16 < W ? r.right + 12 : r.left - S - 12)) + 'px';
      z.style.top = Math.max(8, Math.min(H - S - 8, r.top + r.height / 2 - S / 2)) + 'px';
      z.style.display = 'block';
    });
    document.addEventListener('pointerout', e => { if (ok(e.target)) z.style.display = 'none'; });
    addEventListener('scroll', () => { z.style.display = 'none'; }, true);
  };
  if (typeof document !== 'undefined') SM.coverZoom();

  // Musik-Datenquelle (Wunsch 12.11.2026): ist der Client (Mac, spaeter vielleicht Windows) nicht erreichbar oder der Musikordner (Stick) nicht da, steht oben auf
  // allen Musik-Seiten ein roter Hinweis. Alle 30 s neu geprueft; ist alles wieder da, verschwindet er.
  // Bezeichnung des Rechners mit der Musik (Wunsch 12.11.2026: "Musik-Rechner", nicht "Mac"; auch Windows moeglich), aenderbar in der
  // Uebersetzungstabelle (Einstellungen allgemein -> Panel, Eintrag music_host)
  SM.hostName = async () => {
    if (!SM._hostName) {
      try {
        const d = (await (await fetch('/api/nav')).json()) || {}, v = (d.texts || {}).music_host;   // [deutsch, englisch] oder Text
        SM._hostName = Array.isArray(v) ? (d.lang === 'en' ? v[1] : v[0]) || v[0] : (v || '');
      } catch (e) { /* alter Pi */ }
    }
    return SM._hostName || 'Musik-Rechner';
  };
  SM.sourceCheck = async () => {
    let msg = '';
    const H = await SM.hostName();
    try {
      const m = ((await (await fetch('/api/musik/mac')).json()) || {}).music || '';
      if (!m) msg = '⚠ ' + H + ' nicht erreichbar: Der Light-Butler erreicht den ' + H + ' (Light-Butler Helfer bzw. Mixxx-App) nicht. Vorhören, Tags, Cover, Import und Auto-DJ gehen erst wieder, wenn er läuft.';
      else {
        const st = await (await fetch(m + '/status')).json();
        if (st && st.root_ok === false) msg = '⚠ Musik-Datenquelle nicht erreichbar: Der Musikordner ' + (st.root || '') + ' ist am ' + H + ' nicht da (Stick nicht angesteckt?). Vorhören, Tags, Cover, Import und Auto-DJ gehen erst wieder, wenn er da ist.';
      }
    } catch (e) { msg = '⚠ ' + H + ' nicht erreichbar: Die Musik-Daten am ' + H + ' antworten gerade nicht.'; }
    let el = document.getElementById('srcwarn');
    if (!msg) { if (el) el.remove(); return; }
    // Fest am unteren Rand statt oben eingeschoben (Wunsch 14.11.2026): kommt der Hinweis erst nach dem Laden, darf er die Knoepfe
    // nicht verschieben (man tippte sonst daneben). Ueber der Vorhoer-Leiste; ✕ blendet ihn fuer diese Seite aus.
    if (SM._srcHide) return;
    if (!el) {
      if (!document.getElementById('s2lsrccss')) {
        const st = document.createElement('style'); st.id = 's2lsrccss';
        st.textContent = '#srcwarn{position:fixed;left:12px;right:12px;bottom:12px;z-index:35;display:flex;gap:10px;align-items:flex-start;background:#4a1c1c;color:#ffd6cf;border:1px solid #8a3a32;' +
          'border-radius:8px;padding:8px 12px;font-size:14px;box-shadow:0 6px 24px #000a}body.s2lplaying #srcwarn{bottom:72px}#srcwarn span{flex:1}' +
          '#srcwarn button{flex:none;min-width:30px;min-height:28px;padding:0 8px;background:none;border:1px solid #8a3a32;color:#ffd6cf;border-radius:6px;cursor:pointer}';
        document.head.appendChild(st);
      }
      el = document.createElement('div'); el.id = 'srcwarn';
      el.innerHTML = '<span></span><button type="button" title="Hinweis ausblenden (bis die Seite neu geladen wird)">✕</button>';
      el.querySelector('button').onclick = () => { SM._srcHide = true; el.remove(); };
      document.body.appendChild(el);
    }
    el.querySelector('span').textContent = msg;
  };
  if (typeof document !== 'undefined' && typeof location !== 'undefined' && /^\/musik/.test(location.pathname)) {
    setTimeout(SM.sourceCheck, 800);
    setInterval(SM.sourceCheck, 30000);
  }

  // Verzoegerung der Tonausgabe in ms, soweit der Browser sie kennt (Safari: nicht, dafuer gibt es den Licht-Versatz)
  SM.outputLatency = () => {
    try {
      if (!SM._ac) { const C = window.AudioContext || window.webkitAudioContext; SM._ac = C ? new C() : {}; }
      return ((SM._ac.outputLatency || SM._ac.baseLatency || 0) * 1000) || 0;
    } catch (e) { return 0; }
  };

  // ---- Favoriten (Wunsch 14.11.2026): Herz bei Liedern, Alben, Interpreten, Genres ----
  // Dasselbe Herz wie der Zustand im Hauptpanel. Leer = umrandet, voll = Favorit, halb = Lied eines Lieblings-Albums/-Interpreten.
  // Gemerkt am Pi (showman/favorites.py). SM.favHtml(art, id, {name, artist}) liefert das Herz, ein Tipp schaltet es (alle Seiten gleich).
  // Mit Einstellung fav_mp3 schreibt der Musik-Rechner das Herz eines Liedes zusaetzlich als Bewertung 5 Sterne in die MP3.
  SM.HEART_PATH = 'M7.5 13.5S1 9.6 1 5.2C1 3 2.7 1.5 4.6 1.5c1.2 0 2.3.6 2.9 1.6.6-1 1.7-1.6 2.9-1.6C12.3 1.5 14 3 14 5.2c0 4.4-6.5 8.3-6.5 8.3z';
  const FAV = { st: null, conf: {}, busy: new Set() };
  const favSets = d => { const o = {}; for (const k of ['song', 'album', 'artist', 'genre', 'ind']) o[k] = new Set(d[k] || []); return o; };
  const favApply = (d, why) => {
    FAV.st = favSets(d); FAV.conf = d.conf || FAV.conf;
    SM.favPaint();
    if (typeof document !== 'undefined') document.dispatchEvent(new CustomEvent('s2lfav', { detail: { why: why || 'load' } }));
  };
  SM.favLoad = async () => {
    try { favApply(await SM.get('/api/sm/favs')); } catch (e) { if (!FAV.st) FAV.st = favSets({}); }
    return FAV.st;
  };
  SM.favConf = () => FAV.conf || {};
  SM.favOf = (kind, id) => {
    const s = FAV.st;
    if (!s || !s[kind]) return 0;
    if (kind === 'genre') { const l = String(id).toLowerCase(); for (const g of s.genre) if (g.toLowerCase() === l) return 2; return 0; }
    return s[kind].has(id) ? 2 : kind === 'song' && s.ind.has(id) ? 1 : 0;
  };
  const favTitle = (kind, f) => f === 2 ? 'Favorit · antippen nimmt das Herz weg' : f === 1 ? 'Lied eines Lieblings-' + (kind === 'song' ? 'Albums oder -Interpreten' : '') + ' · antippen: eigenes Herz' : 'Als Favorit markieren';
  const heartSvg = cls => '<svg class="' + cls + '" viewBox="0 0 15 15" aria-hidden="true"><path d="' + SM.HEART_PATH + '"/></svg>';
  SM.favHtml = (kind, id, opt) => {
    favStyle();
    opt = opt || {};
    const f = SM.favOf(kind, id);
    return '<span class="favh f' + f + (opt.cls ? ' ' + opt.cls : '') + '" role="button" tabindex="0" data-fk="' + kind + '" data-fid="' + SM.esc(id) + '"' +
      (opt.name ? ' data-fn="' + SM.esc(opt.name) + '"' : '') + (opt.artist ? ' data-fa="' + SM.esc(opt.artist) + '"' : '') +
      ' title="' + favTitle(kind, f) + '">' + heartSvg('o') + '<span class="fi">' + heartSvg('i') + '</span></span>';
  };
  SM.favPaint = () => {
    if (typeof document === 'undefined') return;
    document.querySelectorAll('.favh').forEach(el => {
      const f = SM.favOf(el.dataset.fk, el.dataset.fid);
      el.classList.remove('f0', 'f1', 'f2'); el.classList.add('f' + f); el.title = favTitle(el.dataset.fk, f);
    });
  };
  let favMusic = '';
  SM.favMp3 = async (path, on) => {                       // Herz als Bewertung in die MP3 (Musik-Rechner)
    if (!favMusic) { try { favMusic = (await SM.get('/api/musik/mac')).music || ''; } catch (e) { favMusic = ''; } }
    if (!favMusic) throw new Error('Musik-Rechner nicht erreichbar');
    const r = await fetch(favMusic + '/tags', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ p: path, name: String(path).split('/').pop(), fields: {}, fav: !!on }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.ok) throw new Error(d.error || ('Fehler ' + r.status));
  };
  SM.favToggle = async (kind, id, meta) => {
    if (!FAV.st) await SM.favLoad();
    const key = kind + '|' + id;
    if (FAV.busy.has(key)) return;
    FAV.busy.add(key);
    const on = SM.favOf(kind, id) !== 2;
    try {
      favApply(await SM.cmd('fav_set', Object.assign({ kind, id, on }, meta || {})), 'set');
      if (kind === 'song' && FAV.conf.mp3 && /\.mp3$/i.test(id)) {
        try { await SM.favMp3(id, on); } catch (e) { SM.toast('Herz gemerkt, in die MP3 ging es nicht: ' + e.message, 5000); }
      }
    } catch (e) { SM.toast('Favorit ging nicht: ' + e.message, 4000); }
    finally { FAV.busy.delete(key); }
  };
  function favStyle() {
    if (typeof document === 'undefined' || document.getElementById('s2lfavcss')) return;
    const st = document.createElement('style'); st.id = 's2lfavcss';
    st.textContent = '.favh{--fs:18px;position:relative;display:inline-flex;flex:none;width:var(--fs);height:var(--fs);cursor:pointer;color:#ff5a7a;vertical-align:middle;-webkit-tap-highlight-color:transparent}' +
      '.favh svg{width:var(--fs);height:var(--fs);display:block}.favh .o path{fill:none;stroke:#9aa0b4;stroke-width:1.4}.favh:hover .o path{stroke:#ff8da3}' +
      '.favh.f1 .o path,.favh.f2 .o path{stroke:currentColor}.favh .fi{position:absolute;left:0;top:0;height:100%;width:0;overflow:hidden}.favh .i path{fill:currentColor}' +
      '.favh.f1 .fi{width:50%}.favh.f2 .fi{width:100%}.favh.sm{--fs:15px;margin-right:5px;top:-1px}.favh.hbig{--fs:24px;margin-left:8px}' +
      '.favh.oncover{position:absolute;top:5px;right:5px;--fs:20px;padding:5px;box-sizing:content-box;border-radius:50%;background:rgba(10,12,20,.62)}' +
      '.favh.oncover .fi{left:5px;top:5px;height:var(--fs)}.favh.oncover .o path{stroke:#e8eaf2}.favh.oncover.f1 .o path,.favh.oncover.f2 .o path{stroke:currentColor}';
    document.head.appendChild(st);
  }
  if (typeof document !== 'undefined') {
    const favClick = e => {
      const el = e.target.closest && e.target.closest('.favh');
      if (!el) return;
      if (e.type === 'keydown' && e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault(); e.stopPropagation();
      SM.favToggle(el.dataset.fk, el.dataset.fid, { name: el.dataset.fn || '', artist: el.dataset.fa || '' });
    };
    document.addEventListener('click', favClick, true);       // vor den Klicks der Kachel (Herz liegt auf dem Cover)
    document.addEventListener('keydown', favClick, true);
  }

  // ---- Sterne setzen (Wunsch 14.11.2026): 0 bis 5 wie in Mixxx. Gemerkt am Pi (showman/stars.py), der Musik-Rechner traegt
  // sie beim naechsten Start der Mixxx-App in Mixxx ein. SM.starsHtml(pfad, sterne) liefert die Reihe, ein Tipp setzt sie
  // (derselbe Stern noch einmal = keine Sterne). 5 Sterne zaehlen als Favorit.
  function starsStyle() {
    if (typeof document === 'undefined' || document.getElementById('s2lstcss')) return;
    const st = document.createElement('style'); st.id = 's2lstcss';
    st.textContent = '.lbst{display:inline-flex;gap:0;white-space:nowrap;vertical-align:middle;cursor:pointer;font-size:13px;line-height:1}.lbst b{font-weight:400;color:#3a3f58;padding:0 1px}' +
      '.lbst b.on{color:#f0c040}@media (hover:hover){.lbst:hover b{color:#f0c040}.lbst b:hover~b{color:#3a3f58}}.lbst.big{font-size:20px;margin-left:10px}' +
      '.lbstpick{position:absolute;z-index:70;display:flex;gap:4px;padding:6px;background:var(--pan,#22253a);border:1px solid var(--line,#333);border-radius:10px;box-shadow:0 8px 24px #000a}' +
      '.lbstpick button{min-height:30px;padding:2px 8px;font-size:13px}';
    document.head.appendChild(st);
  }
  SM.starsHtml = (path, r, cls) => {
    starsStyle();
    r = Math.max(0, Math.min(5, +r || 0));
    let h = '';
    for (let n = 1; n <= 5; n++) h += '<b data-n="' + n + '"' + (n <= r ? ' class="on"' : '') + '>★</b>';
    return '<span class="lbst' + (cls ? ' ' + cls : '') + '" data-sp="' + SM.esc(path) + '" data-r="' + r + '" title="Sterne (wie in Mixxx): antippen setzt, derselbe Stern noch einmal = keine">' + h + '</span>';
  };
  SM.starSet = async (paths, r) => {
    paths = (paths || []).filter(Boolean);
    if (!paths.length) return;
    let d;
    try { d = await SM.cmd('stars_set', { paths, r }); } catch (e) { SM.toast('Sterne gingen nicht: ' + e.message, 4000); return; }
    const set = new Set(paths);
    document.querySelectorAll('.lbst').forEach(el => {
      if (!set.has(el.dataset.sp)) return;
      el.dataset.r = r;
      el.querySelectorAll('b').forEach(b => b.classList.toggle('on', +b.dataset.n <= r));
    });
    if (d && d.song) favApply(d, 'set');                    // 5 Sterne = Favorit: Herzen gleich nachziehen
    if (typeof document !== 'undefined') document.dispatchEvent(new CustomEvent('s2lstars', { detail: { paths, r } }));
    SM.toast((paths.length > 1 ? paths.length + ' Lieder: ' : '') + (r ? r + ' Stern' + (r === 1 ? '' : 'e') : 'keine Sterne') + ' · kommt beim nächsten Start der Mixxx-App in Mixxx', 3500);
  };
  // Auswahl 0-5 unter einem Knopf ("Alle ★ …"): Promise mit der Zahl oder null
  SM.starsPick = btn => new Promise(res => {
    starsStyle();
    document.querySelectorAll('.lbstpick').forEach(x => x.remove());
    const m = document.createElement('div'); m.className = 'lbstpick';
    m.innerHTML = [5, 4, 3, 2, 1].map(n => '<button data-n="' + n + '">' + '★'.repeat(n) + '</button>').join('') + '<button data-n="0">keine</button>';
    const r = btn.getBoundingClientRect();
    m.style.left = Math.max(8, Math.min(innerWidth - 330, r.left + scrollX)) + 'px'; m.style.top = (r.bottom + scrollY + 4) + 'px';
    document.body.appendChild(m);
    const done = v => { m.remove(); document.removeEventListener('click', away, true); res(v); };
    const away = e => { if (!m.contains(e.target)) done(null); };
    m.addEventListener('click', e => { const b = e.target.closest('button'); if (b) done(+b.dataset.n); });
    setTimeout(() => document.addEventListener('click', away, true), 0);
  });
  if (typeof document !== 'undefined') {
    document.addEventListener('click', e => {
      const b = e.target.closest && e.target.closest('.lbst b');
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      const el = b.parentElement, n = +b.dataset.n;
      SM.starSet([el.dataset.sp], n === +el.dataset.r ? 0 : n);
    }, true);
  }

  // ---- In den Auto-DJ (Wunsch 14.11.2026): einzelne Lieder als Naechstes, ganze Listen hinten an die Playlist ----
  // Laeuft der Auto-DJ (eigenes Fenster), meldet er sich alle 2 s ueber den BroadcastChannel 'lb_autodj'; sonst kommt die
  // Liste in eine Warteliste (localStorage), das Auto-DJ-Fenster geht auf und nimmt sie beim Start. Wie in der Musik-Datenbank.
  const ADJ = { bc: null, seen: 0, wait: [], sent: 0 };
  SM.autodjWatch = () => {
    if (ADJ.bc || typeof BroadcastChannel === 'undefined') return;
    ADJ.bc = new BroadcastChannel('lb_autodj');
    ADJ.bc.onmessage = e => {
      const d = e.data || {};
      if (d.type === 'alive') { ADJ.seen = Date.now(); ADJ.wait.splice(0).forEach(f => f()); }
      if (Date.now() - ADJ.sent > 4000) return;              // Antwort gilt einer anderen Seite (Musik-DB hat ihren eigenen Hinweis)
      if (d.type === 'ok') SM.toast('Im Auto-DJ als Nächstes: ' + (d.name || ''), 3500);
      if (d.type === 'added') SM.toast(d.n + ' Lied' + (d.n === 1 ? '' : 'er') + ' hinten an die Playlist angehängt' + (d.skip ? ' (' + d.skip + ' standen schon drin)' : ''), 4000);
    };
  };
  SM.adjTrack = r => ({ path: r.path, title: r.title, artist: r.artist, name: r.name, dur: r.dur, bpm: r.bpm, kid: r.kid, lvl: r.lvl, est: r.est, elv: r.elv, genre: r.genre });
  SM.autodjAdd = async (rows, next, src) => {
    SM.autodjWatch();
    const ts = (rows || []).filter(r => r && r.path).map(SM.adjTrack);
    if (!ts.length) return;
    if (Date.now() - ADJ.seen > 5000 && ADJ.bc) {           // noch nicht gehoert: kurz auf das Lebenszeichen warten
      await new Promise(res => { ADJ.wait.push(res); setTimeout(res, 2300); });
    }
    if (ADJ.bc && Date.now() - ADJ.seen < 5000) {
      ADJ.sent = Date.now();
      if (next) ts.forEach(t => ADJ.bc.postMessage({ type: 'next', t }));
      else ADJ.bc.postMessage({ type: 'add', ts, src: src || '' });
      return;
    }
    try {
      if (next) {
        const q = JSON.parse(localStorage.getItem('autodj_next') || '[]');
        localStorage.setItem('autodj_next', JSON.stringify(q.concat(ts).slice(-50)));
      } else {
        const q = JSON.parse(localStorage.getItem('autodj_add') || '[]');
        q.push({ ts: ts.slice(0, 500), src: src || '' });
        localStorage.setItem('autodj_add', JSON.stringify(q.slice(-10)));
      }
    } catch (e) { /* privates Fenster */ }
    SM.toast((next ? 'Kommt im Auto-DJ als Nächstes: ' + (ts[0].name || ts[0].title || '') : ts.length + ' Lied' + (ts.length === 1 ? '' : 'er') + ' kommen hinten an die Playlist') + ' (Auto-DJ geht auf)', 4000);
    if (window.S2LNav && window.S2LNav.openAutoDJ) window.S2LNav.openAutoDJ();
  };
  if (typeof document !== 'undefined' && typeof location !== 'undefined' && /^\/musik/.test(location.pathname) && !/autodj/.test(location.pathname)) SM.autodjWatch();

  if (typeof module !== 'undefined' && module.exports) module.exports = SM;
  root.SM = SM;
})(typeof window !== 'undefined' ? window : globalThis);
