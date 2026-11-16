// timeline.js - die grafische Timeline: Zeichnen (nur was sichtbar ist) und Bedienung per Maus und Touch.
(function () {
  'use strict';
  const SM = window.SM;
  const MARK_SEC = { intro: ['Intro', '#3f8f9f'], vers: ['Strophe', '#6b7390'], main: ['Main', '#3fbf6f'], break: ['Break', '#d9853f'], outro: ['Outro', '#3f8f9f'] };
  const MARK_SNAP_PX = 8;                    // so nah rastet ein Clip an Cue oder Abschnittsgrenze ein
  const RULER = 24, WAVE = 58, SCENE = 30, PANEL = 26, MASTER = 30, ROW = 36, HEAD = 22, HEAD_FOLDED = 32;
  // Pegelkurven der getrennten Spuren (vom Mac, shows/_stems): nur Anzeige, aufs Licht wirken sie nicht
  const STEM_ROW = 16, STEM_FLOOR = 51;      // 51 von 255 = -48 dB: leiser zeigt nichts
  const STEMS = [['stimme', 'Stimme', '#ff5fa2'], ['bass', 'Bass', '#7d8cff'], ['kick', 'Kick', '#ff9f43'], ['hihat', 'Snare/Hi-Hat', '#ffe066'], ['sonstiges', 'Sonstiges', '#3ddc6a']];
  const COLORS = ['#ff7a59', '#4aa8ff', '#3ddc6a', '#c58bff', '#ffc83d', '#ff5fa2', '#2fd4c6', '#a0d911', '#ff9f43', '#7d8cff'];
  const RAINBOW = ['#ff2d2d', '#ff9f1a', '#ffe11a', '#2ecc40', '#1ac8ff', '#3d5cff', '#c23dff', '#ff2d9b'];
  const GLYPH = { circle: '○', eight: '∞', sweep_lr: '↔', sweep_ud: '↕', sine_move: '∿', random_move: '⁂', fan: '⋔' };
  const SWEEP = ['ktv_size', 'ktv_rotate', 'ktv_pos_x', 'ktv_pos_y', 'ktv_fan'];
  const hashColor = s => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0; return COLORS[h % COLORS.length]; };

  SM.Timeline = class {
    constructor(host, opts) {
      this.host = host; this.o = opts;
      this.base = host.querySelector('#base'); this.over = host.querySelector('#over');
      this.ctx = this.base.getContext('2d'); this.octx = this.over.getContext('2d');
      this.t0 = 0; this.pxs = 12; this.sy = 0;
      this.hw = 170;
      this.doc = null; this.peaks = null; this.sel = new Set(); this.collapsed = new Set(); this.selTrack = null;
      this.pos = 0; this.multi = false;
      this.ptr = new Map(); this.drag = null; this.lastTap = null;
      this.need = true;
      new ResizeObserver(() => this.resize()).observe(host);
      this.resize();
      const m = host;
      m.addEventListener('pointerdown', e => this.down(e));
      m.addEventListener('pointermove', e => this.move(e));
      m.addEventListener('pointerup', e => this.up(e));
      m.addEventListener('pointercancel', e => this.up(e, true));
      m.addEventListener('wheel', e => this.wheel(e), { passive: false });
      m.addEventListener('contextmenu', e => e.preventDefault());
      const loop = () => {
        if (this.o.onFrame) this.o.onFrame();      // zuerst die Position, sonst zeigt die Linie immer das Bild davor
        if (this.need) { this.need = false; this.draw(); }
        this.drawOver();
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    }

    // ---- Geometrie -------------------------------------------------------------------------------
    resize() {
      const r = this.host.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      this.w = r.width; this.h = r.height; this.hw = r.width < 560 ? 104 : 170;
      for (const c of [this.base, this.over]) { c.width = r.width * dpr; c.height = r.height * dpr; }
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0); this.octx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (this.doc) { this.clampView(); this.draw(); this.drawOver(); }     // sofort, sonst blitzt die leere Flaeche kurz auf
      this.need = false;
    }
    x(t) { return this.hw + (t - this.t0) * this.pxs; }
    t(x) { return this.t0 + (x - this.hw) / this.pxs; }
    top() { return this.wb() + SCENE + PANEL + MASTER; }
    stemH() { return this.stems && this.showStems !== false ? STEMS.length * STEM_ROW : 0; }
    wb() { return RULER + WAVE + this.stemH(); }
    setStems(d) {
      this.stems = null;
      if (d && d.curves && d.rate) {
        const c = {};
        for (const [k] of STEMS) c[k] = Uint8Array.from(atob(d.curves[k] || ''), ch => ch.charCodeAt(0));
        this.stems = { rate: d.rate, c };
      }
      this.clampView(); this.need = true;
    }
    setDoc(doc) { this.doc = doc; SM.masterTrack(doc); SM.panelTrack(doc); this.sel = new Set([...this.sel].filter(id => SM.find(doc, id))); this.rebuild(); }
    rebuild() {
      const rows = []; let y = 0;
      const seen = new Set();
      for (const tr of this.doc.tracks) {
        if (SM.isPinned(tr)) continue;           // steht fest oben, scrollt nicht mit
        const key = SM.targetKey(tr.target);
        if (!seen.has(key)) {
          seen.add(key);
          const h = this.collapsed.has(key) ? HEAD_FOLDED : HEAD;
          rows.push({ type: 'head', key, target: tr.target, y, h, color: hashColor(key), label: this.o.targetLabel(tr.target) });
          y += h;
        }
        if (!this.collapsed.has(key)) {
          rows.push({ type: 'track', track: tr, key, y, h: ROW, color: hashColor(key), label: this.o.attrLabel(tr) });
          y += ROW;
        }
      }
      this.rows = rows; this.rowsH = y;
      this.clampView();
      this.need = true;
    }
    maxT() { return Math.max(this.doc ? this.doc.duration : 60, 10); }
    clampView() {
      const span = (this.w - this.hw) / this.pxs;
      this.t0 = SM.clamp(this.t0, 0, Math.max(0, this.maxT() - span * 0.5));
      this.sy = SM.clamp(this.sy, 0, Math.max(0, this.rowsH - (this.h - this.top()) + 20));
    }
    zoom(f, at) {
      at = at === undefined ? this.hw + (this.w - this.hw) / 2 : at;
      const t = this.t(at);
      this.pxs = SM.clamp(this.pxs * f, Math.max(0.2, (this.w - this.hw) / this.maxT() * 0.9), 800);
      this.t0 = t - (at - this.hw) / this.pxs;
      this.clampView(); this.need = true;
    }
    visible(t0, t1) { return t1 > this.t0 && t0 < this.t(this.w); }
    fit() { this.pxs = Math.max(0.2, (this.w - this.hw) / this.maxT()); this.t0 = 0; this.need = true; }
    follow(t) {
      if (this.userView) return;                 // selbst weggescrollt: die Ansicht bleibt, bis du springst oder neu startest
      const span = (this.w - this.hw) / this.pxs;
      if (t < this.t0 || t > this.t0 + span * 0.92) { this.t0 = Math.max(0, t - span * 0.08); this.clampView(); this.need = true; }
    }
    masterRow() {                                 // y so, dass vy und uy die feste Zeile treffen, egal wie weit gescrollt ist
      return { type: 'track', master: true, pinned: true, track: SM.masterTrack(this.doc), key: 'master', y: this.sy - MASTER, h: MASTER, color: '#ffd24d', label: 'Master' };
    }
    panelRow() {
      return { type: 'track', panel: true, pinned: true, track: SM.panelTrack(this.doc), key: 'panel', y: this.sy - MASTER - PANEL, h: PANEL, color: '#6b4bbf', label: 'Panel-Szenen' };
    }
    foldKeys() { return [...new Set(this.doc.tracks.filter(t => !SM.isPinned(t)).map(t => SM.targetKey(t.target)))]; }
    allFolded() { const k = this.foldKeys(); return k.length > 0 && k.every(x => this.collapsed.has(x)); }
    foldAll() {                                   // schneller Ueberblick: alle Geraete auf die Hauptzeile, nochmal = alle wieder auf
      if (this.allFolded()) this.collapsed.clear(); else this.collapsed = new Set(this.foldKeys());
      this.o.onFold([...this.collapsed]);
      this.rebuild();
    }
    rowAt(y) {
      if (y >= this.top() - MASTER && y < this.top()) return this.masterRow();
      if (y >= this.top() - MASTER - PANEL && y < this.top() - MASTER) return this.panelRow();
      const yy = y - this.top() + this.sy;
      return this.rows.find(r => yy >= r.y && yy < r.y + r.h) || null;
    }
    // Wert 0..1 einer Spur auf die Hoehe der Zeile
    vy(row, u) { return this.top() - this.sy + row.y + row.h - 4 - u * (row.h - 8); }
    uy(row, y) { return SM.clamp((this.top() - this.sy + row.y + row.h - 4 - y) / (row.h - 8), 0, 1); }

    hit(x, y) {
      if (y < this.wb()) return x > this.hw ? { zone: 'ruler' } : { zone: 'corner', btn: y < RULER ? 'fold' : this.stems && x < 84 && y >= RULER + WAVE - 18 && y < RULER + WAVE ? 'stems' : '' };
      if (y < this.wb() + SCENE) {
        if (x <= this.hw) return { zone: 'scenehead' };
        const sc = SM.hitClip(this.doc.scene_clips, x, t => this.x(t));
        return sc ? { zone: 'scene', id: sc.ev.id, ev: sc.ev, edge: sc.edge } : { zone: 'sceneempty' };
      }
      const row = this.rowAt(y);
      if (!row) return { zone: 'empty' };
      if (x <= this.hw) {
        if (row.type === 'head') return { zone: 'head', row, btn: x > this.hw - 24 ? 'del' : '' };
        return { zone: 'trackhead', row, btn: row.pinned ? '' : x > this.hw - 24 ? 'del' : x > this.hw - 48 ? 'mute' : '' };
      }
      if (row.type === 'head') return { zone: 'headlane', row };
      const tr = row.track;
      // Keyframes zuerst: sie liegen oben. Treffer etwas groesser fuer Finger.
      const scalar = SM.kindOf(tr.attr) === 'scalar' && !this.o.stepped(tr);
      let best = null, bd = 196;
      for (const k of tr.keys) {
        const kx = this.x(k.t);
        if (Math.abs(kx - x) > 14) continue;
        const ky = scalar ? this.vy(row, k.v / 255) : this.top() - this.sy + row.y + row.h / 2;
        const d = (kx - x) * (kx - x) + (ky - y) * (ky - y);
        if (d < bd) { bd = d; best = k; }
      }
      if (best) return { zone: 'key', row, track: tr, id: best.id, ev: best };
      const cl = SM.hitClip(tr.clips, x, t => this.x(t));
      if (cl) return { zone: 'clip', row, track: tr, id: cl.ev.id, ev: cl.ev, edge: cl.edge };
      return { zone: 'lane', row, track: tr };
    }

    // ---- Zeichnen ----------------------------------------------------------------------------------
    draw() {
      const g = this.ctx, W = this.w, H = this.h, hw = this.hw;
      g.clearRect(0, 0, W, H);
      g.fillStyle = '#0b0c12'; g.fillRect(0, 0, W, H);
      if (!this.doc) return;
      const doc = this.doc, T0 = this.t0, T1 = this.t(W), top = this.top();
      this.drawRows(g, T0, T1, top);
      this.drawBands(g, top, H);
      this.drawGrid(g, T0, T1, top, H);
      this.drawEvents(g, T0, T1, top);
      this.drawWave(g, T0, T1);
      this.drawStems(g);
      this.drawScenes(g, T0, T1);
      this.drawPanel(g, T0, T1);
      this.drawMaster(g, T0, T1);
      this.drawRuler(g, T0, T1);
      this.drawCues(g, H);
      this.drawLoop(g, H);
      // Ende der Show
      const ex = this.x(doc.duration);
      if (ex < W) {
        g.fillStyle = '#0008'; g.fillRect(Math.max(hw, ex), 0, W - Math.max(hw, ex), H);
        g.fillStyle = '#ff5a4d'; g.fillRect(ex, 0, 1, H);
      }
      // linke Spalte zuletzt, sie deckt alles Hineinragende ab
      g.save(); g.beginPath(); g.rect(0, top, hw, H - top); g.clip();
      g.fillStyle = '#171923'; g.fillRect(0, top, hw, H - top);
      g.font = '600 12px Inter,sans-serif'; g.textBaseline = 'middle';
      for (const r of this.rows) {
        const y = top - this.sy + r.y;
        if (y + r.h < top || y > H) continue;
        if (r.type === 'head') {
          g.fillStyle = '#23263a'; g.fillRect(0, y, hw, r.h);
          g.fillStyle = r.color; g.fillRect(0, y, 3, r.h);
          g.fillStyle = '#cfd3e6'; g.fillText((this.collapsed.has(r.key) ? '▸ ' : '▾ ') + this.fit_(g, r.label, hw - 44), 8, y + r.h / 2);
          g.fillStyle = '#7d8299'; g.fillText('×', hw - 16, y + r.h / 2);
        } else {
          const sel = this.selTrack === r.track.id;
          g.fillStyle = sel ? '#2b2f48' : '#191b27'; g.fillRect(0, y, hw, r.h - 1);
          g.fillStyle = r.color; g.fillRect(0, y, 3, r.h);
          g.fillStyle = r.track.mute ? '#5a5f76' : '#e4e7f3'; g.fillText(this.fit_(g, r.label, hw - 66), 12, y + r.h / 2);
          g.fillStyle = r.track.mute ? '#ff9f43' : '#6a6f88'; g.fillText('M', hw - 42, y + r.h / 2);
          g.fillStyle = '#7d8299'; g.fillText('×', hw - 16, y + r.h / 2);
        }
      }
      g.restore();
      g.fillStyle = '#171923'; g.fillRect(0, 0, hw, top);
      g.fillStyle = '#8a90a8'; g.font = '600 11px Inter,sans-serif'; g.textBaseline = 'middle';
      if (this.foldKeys().length) {
        g.fillStyle = '#23263a'; this.round(g, 6, 3, 76, RULER - 6, 4); g.fill();
        g.fillStyle = '#cfd3e6'; g.fillText(this.allFolded() ? '▸ Alle auf' : '▾ Alle zu', 12, RULER / 2);
        g.fillStyle = '#8a90a8';
      }
      g.fillText('Musik', 10, RULER + WAVE / 2);
      if (this.stems) {
        g.fillStyle = '#23263a'; this.round(g, 6, RULER + WAVE - 17, 72, 14, 4); g.fill();
        g.fillStyle = '#cfd3e6'; g.font = '600 10px Inter,sans-serif'; g.fillText(this.stemH() ? '▾ Kurven' : '▸ Kurven', 11, RULER + WAVE - 10);
        STEMS.forEach(([, label, color], i) => { if (!this.stemH()) return; g.fillStyle = color; g.fillText(label, 10, RULER + WAVE + i * STEM_ROW + STEM_ROW / 2); });
        g.font = '600 11px Inter,sans-serif'; g.fillStyle = '#8a90a8';
      }
      g.fillText('Szenen', 10, this.wb() + SCENE / 2);
      g.fillStyle = this.selTrack === SM.panelTrack(doc).id ? '#c6b3ff' : '#8a90a8';
      g.fillText('Panel-Szenen', 10, this.wb() + SCENE + PANEL / 2);
      g.fillStyle = this.selTrack === SM.masterTrack(doc).id ? '#ffd24d' : '#8a90a8';
      g.fillText('Master', 10, this.wb() + SCENE + PANEL + MASTER / 2);
      g.fillStyle = '#2c2f42'; g.fillRect(hw, 0, 1, H); g.fillRect(0, top - 1, W, 1);
      if (!this.rows.length) {
        g.fillStyle = '#8a90a8'; g.font = '500 14px Inter,sans-serif'; g.textAlign = 'center';
        g.fillText('Fixture aus der Liste hierher ziehen', hw + (W - hw) / 2, top + 50);
        g.textAlign = 'left';
      }
    }
    fit_(g, s, w) {
      if (g.measureText(s).width <= w) return s;
      while (s.length > 1 && g.measureText(s + '…').width > w) s = s.slice(0, -1);
      return s + '…';
    }
    drawRows(g, T0, T1, top) {
      const W = this.w, H = this.h;
      g.save(); g.beginPath(); g.rect(this.hw, top, W - this.hw, H - top); g.clip();
      for (const r of this.rows) {
        const y = top - this.sy + r.y;
        if (y + r.h < top || y > H) continue;
        g.fillStyle = r.type === 'head' ? '#14151f' : (this.selTrack === (r.track && r.track.id) ? '#181b2b' : '#10111a');
        g.fillRect(this.hw, y, W - this.hw, r.h - 1);
      }
      g.restore();
    }
    drawGrid(g, T0, T1, top, H) {
      const lines = SM.gridLines(this.doc, this.doc.grid, this.pxs);
      if (!lines) return;                       // Raster aus: keine Linien
      const { minor, major, off } = lines;
      let i = Math.floor((T0 - off) / minor);
      g.save(); g.beginPath(); g.rect(this.hw, RULER, this.w - this.hw, H - RULER); g.clip();
      for (; ; i++) {
        const t = off + i * minor;
        if (t > T1) break;
        const isMajor = Math.abs((t - off) / major - Math.round((t - off) / major)) < 1e-6;
        g.fillStyle = isMajor ? '#2a2d42' : '#1a1c29';
        g.fillRect(Math.round(this.x(t)), RULER, 1, H - RULER);
      }
      g.restore();
    }
    drawLoop(g, H) {
      const L = this.loop;
      if (!L) return;
      const a = Math.max(this.hw, this.x(L.t0)), b = Math.min(this.w, this.x(L.t1));
      if (b <= a) return;
      if (L.on) { g.fillStyle = '#e8710a18'; g.fillRect(a, RULER, b - a, H - RULER); }
      g.fillStyle = L.on ? '#e8710a' : '#5a5f76';
      g.fillRect(a, 0, b - a, 7);
      for (const t of [L.t0, L.t1]) {
        const x = this.x(t);
        if (x >= this.hw && x <= this.w) { g.fillRect(x - 1, 0, 2, RULER); if (L.on) g.fillRect(x - 0.5, RULER, 1, H - RULER); }
      }
    }
    drawRuler(g, T0, T1) {
      const W = this.w, hw = this.hw;
      g.fillStyle = '#171923'; g.fillRect(hw, 0, W - hw, RULER);
      g.fillStyle = '#8a90a8'; g.font = '500 10px Inter,sans-serif'; g.textBaseline = 'middle';
      const nice = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800];
      const st = nice.find(s => s * this.pxs >= 64) || 3600;
      for (let t = Math.floor(T0 / st) * st; t <= T1; t += st) {
        const x = this.x(t);
        if (x < hw) continue;
        g.fillRect(Math.round(x), RULER - 6, 1, 6);
        const m = Math.floor(t / 60), s = t - m * 60;
        g.fillText(m + ':' + (s < 10 ? '0' : '') + (st < 1 ? s.toFixed(2) : s.toFixed(0)), x + 3, RULER / 2 - 2);
      }
    }
    drawWave(g, T0, T1) {
      const W = this.w, hw = this.hw, y0 = RULER, h = WAVE, mid = y0 + h / 2, p = this.peaks;
      g.fillStyle = '#0d0e16'; g.fillRect(hw, y0, W - hw, h);
      this.sections().forEach(s => { g.globalAlpha = 0.3; g.fillStyle = s.color; g.fillRect(s.a, y0, s.b - s.a, h); g.globalAlpha = 1; });
      if (p && p.min && p.min.length) {
        g.fillStyle = '#3f7fd0';
        const rate = p.rate, sc = h / 2 / 127;
        for (let x = Math.max(hw, this.x(0)); x < W; x++) {
          const a = this.t(x), b = this.t(x + 1);
          let i = Math.floor(a * rate), j = Math.ceil(b * rate);
          if (i >= p.min.length) break;
          j = Math.min(Math.max(j, i + 1), p.min.length);
          let mn = 127, mx = -127;
          const stride = Math.max(1, Math.floor((j - i) / 24));       // weit herausgezoomt: nicht jeden Wert lesen
          for (let k = i; k < j; k += stride) {
            if (p.min[k] < mn) mn = p.min[k];
            if (p.max[k] > mx) mx = p.max[k];
          }
          g.fillRect(x, mid - mx * sc, 1, Math.max(1, (mx - mn) * sc));
        }
      } else {
        g.fillStyle = '#5a5f76'; g.font = '500 12px Inter,sans-serif';
        g.fillText(this.doc.audio ? 'keine Wellenform' : 'Noch keine Musik: oben „MP3“ wählen', hw + 12, mid);
      }
      g.font = '600 11px Inter,sans-serif'; g.textBaseline = 'middle';
      for (const s of this.sections()) {
        const tw = g.measureText(s.label).width + 8;
        if (s.b - s.a < tw + 4) continue;
        g.fillStyle = '#12131dcc'; g.fillRect(s.a + 2, y0 + 2, tw, 14);
        g.fillStyle = '#fff'; g.fillText(s.label, s.a + 6, y0 + 9);
      }
      this.drawLyrics(g, y0, h);
      g.fillStyle = '#2c2f42'; g.fillRect(hw, y0 + h - 1, W - hw, 1);
    }
    // Je Spur eine schmale Zeile, der Spitzenwert je Bildpunkt als Saeule von unten
    drawStems(g) {
      const hgt = this.stemH();
      if (!hgt) return;
      const W = this.w, hw = this.hw, y0 = RULER + WAVE, S = this.stems, rate = S.rate;
      g.fillStyle = '#0d0e16'; g.fillRect(hw, y0, W - hw, hgt);
      STEMS.forEach(([key, , color], r) => {
        const v = S.c[key], yb = y0 + (r + 1) * STEM_ROW - 1, sc = (STEM_ROW - 2) / (255 - STEM_FLOOR);
        if (!v || !v.length) return;
        g.fillStyle = color;
        for (let x = Math.max(hw, Math.floor(this.x(0))); x < W; x++) {
          let i = Math.floor(this.t(x) * rate), j = Math.ceil(this.t(x + 1) * rate);
          if (i >= v.length) break;
          if (i < 0) continue;
          j = Math.min(Math.max(j, i + 1), v.length);
          let m = 0;
          const stride = Math.max(1, Math.floor((j - i) / 24));
          for (let k = i; k < j; k += stride) if (v[k] > m) m = v[k];
          if (m > STEM_FLOOR) g.fillRect(x, yb - (m - STEM_FLOOR) * sc, 1, (m - STEM_FLOOR) * sc);
        }
        g.fillStyle = '#1c1f2c'; g.fillRect(hw, yb, W - hw, 1);
      });
    }
    // Liedzeilen unten in der Wellenform: jede Zeile an ihrer Stelle, gekuerzt bis zur naechsten
    drawLyrics(g, y0, h) {
      const L = this.marks() !== null || this.showMarks !== false ? (this.doc.lyrics || {}).lines : null;
      if (!L || !L.length || this.showMarks === false) return;
      const yy = y0 + h - 15, W = this.w, hw = this.hw;
      g.font = '500 10px Inter,sans-serif'; g.textBaseline = 'middle';
      for (let i = 0; i < L.length; i++) {
        if (!L[i][1]) continue;                   // Leerzeile: hier ist nur Schluss
        const a = this.x(L[i][0]), b = this.x(SM.lyricEnd(L, i));
        if (b < hw || a > W) continue;
        const ax = Math.max(a, hw), bx = Math.min(b, W);       // der Balken zeigt, wie lange die Zeile dauert
        g.fillStyle = '#2e4a78e6'; g.fillRect(ax, yy, Math.max(1, bx - ax - 1), 13);
        g.fillStyle = '#7fb0ff'; g.fillRect(ax, yy, 1, 13);
        if (bx - ax < 18) continue;
        g.fillStyle = '#f0f3fb'; g.fillText(this.fit_(g, L[i][1], bx - ax - 7), ax + 4, yy + 7);
      }
    }
    // Abschnitte und Cues des Liedes (aus Mixxx): nur Anzeige und Einrasten, aufs Licht wirken sie nie
    marks() { return this.showMarks !== false && this.doc ? this.doc.marks || null : null; }
    sections() {
      const m = this.marks(), out = [];
      for (const s of m ? m.se : []) {
        const a = Math.max(this.hw, this.x(s[1])), b = Math.min(this.w, this.x(s[2]));
        if (b > a && MARK_SEC[s[0]]) out.push({ a, b, label: MARK_SEC[s[0]][0], color: MARK_SEC[s[0]][1] });
      }
      return out;
    }
    drawBands(g, top, H) {
      g.globalAlpha = 0.14;
      for (const s of this.sections()) { g.fillStyle = s.color; g.fillRect(s.a, top, s.b - s.a, H - top); }
      g.globalAlpha = 1;
    }
    drawCues(g, H) {
      const m = this.marks();
      if (!m) return;
      g.font = '600 10px Inter,sans-serif'; g.textBaseline = 'middle'; g.textAlign = 'center';
      let last = -1e9;
      m.cu.forEach((c, i) => {
        const x = this.x(c);
        if (x < this.hw || x > this.w) return;
        g.globalAlpha = 0.55; g.fillStyle = '#ffd24d'; g.fillRect(x - 0.5, RULER, 1, H - RULER); g.globalAlpha = 1;
        if (x - last < 16) return;                 // weit herausgezoomt: nur die Linie
        last = x;
        g.fillStyle = '#ffd24d'; g.beginPath(); g.moveTo(x - 7, 3); g.lineTo(x + 7, 3); g.lineTo(x + 7, 15); g.lineTo(x, RULER); g.lineTo(x - 7, 15); g.fill();
        g.fillStyle = '#12131d'; g.fillText(String(i + 1), x, 9.5);
      });
      g.textAlign = 'left';
    }
    drawScenes(g, T0, T1) {
      const y = this.wb(), h = SCENE, doc = this.doc;
      g.save(); g.beginPath(); g.rect(this.hw, y, this.w - this.hw, h); g.clip();
      g.fillStyle = '#12131d'; g.fillRect(this.hw, y, this.w - this.hw, h);
      g.font = '600 11px Inter,sans-serif'; g.textBaseline = 'middle';
      for (const c of doc.scene_clips) {
        if (c.t > T1 || c.t + c.d < T0) continue;
        const a = this.x(c.t), b = this.x(c.t + c.d), s = doc.scenes.find(z => z.id === c.scene);
        g.fillStyle = '#6b4bbf'; this.round(g, a, y + 3, b - a, h - 6, 4); g.fill();
        this.fades(g, a, b, y + 3, h - 6, c.fade_in, c.fade_out);
        if (this.sel.has(c.id)) { g.strokeStyle = '#ffb35c'; g.lineWidth = 2; this.round(g, a, y + 3, b - a, h - 6, 4); g.stroke(); }
        g.fillStyle = '#fff'; if (b - a > 26) g.fillText(this.fit_(g, s ? s.name : '?', b - a - 10), a + 5, y + h / 2);
      }
      g.restore();
    }
    round(g, x, y, w, h, r) {
      g.beginPath();
      if (g.roundRect) g.roundRect(x, y, Math.max(1, w), h, Math.min(r, Math.abs(w) / 2)); else g.rect(x, y, Math.max(1, w), h);
    }
    fades(g, a, b, y, h, fi, fo) {
      g.fillStyle = '#0006';
      if (fi > 0) { const x = Math.min(b, a + fi * this.pxs); g.beginPath(); g.moveTo(a, y); g.lineTo(x, y); g.lineTo(a, y + h); g.fill(); }
      if (fo > 0) { const x = Math.max(a, b - fo * this.pxs); g.beginPath(); g.moveTo(b, y); g.lineTo(x, y); g.lineTo(b, y + h); g.fill(); }
    }
    drawPanel(g, T0, T1) {
      const r = this.panelRow(), y = this.wb() + SCENE, W = this.w;
      g.save(); g.beginPath(); g.rect(this.hw, y, W - this.hw, PANEL); g.clip();
      g.fillStyle = this.selTrack === r.track.id ? '#181b2b' : '#12131d'; g.fillRect(this.hw, y, W - this.hw, PANEL);
      if (r.track.clips.length) { g.font = '600 11px Inter,sans-serif'; g.textBaseline = 'middle'; this.drawClips(g, r.track, r, y, T0, T1); }
      else {
        g.fillStyle = '#5a5f76'; g.font = '500 11px Inter,sans-serif'; g.textBaseline = 'middle';
        g.fillText('Doppelt antippen setzt eine Szene aus dem Hauptpanel', this.hw + 8, y + PANEL / 2);
      }
      g.fillStyle = '#2c2f42'; g.fillRect(this.hw, y + PANEL - 1, W - this.hw, 1);
      g.restore();
    }
    drawMaster(g, T0, T1) {
      const r = this.masterRow(), y = this.wb() + SCENE + PANEL, W = this.w;
      g.save(); g.beginPath(); g.rect(this.hw, y, W - this.hw, MASTER); g.clip();
      g.fillStyle = this.selTrack === r.track.id ? '#181b2b' : '#12131d'; g.fillRect(this.hw, y, W - this.hw, MASTER);
      if (r.track.keys.length) this.drawKeys(g, r.track, r, y, T0, T1);
      else {
        g.fillStyle = '#5a5f76'; g.font = '500 11px Inter,sans-serif'; g.textBaseline = 'middle';
        g.fillText('100 %: doppelt antippen setzt einen Keyframe', this.hw + 8, y + MASTER / 2);
      }
      g.fillStyle = '#2c2f42'; g.fillRect(this.hw, y + MASTER - 1, W - this.hw, 1);
      g.restore();
    }
    drawEvents(g, T0, T1, top) {
      const H = this.h;
      g.save(); g.beginPath(); g.rect(this.hw, top, this.w - this.hw, H - top); g.clip();
      g.font = '600 11px Inter,sans-serif'; g.textBaseline = 'middle';
      for (const r of this.rows) {
        const y = top - this.sy + r.y;
        if (y + r.h < top || y > H) continue;
        if (r.type === 'head') {
          if (this.collapsed.has(r.key)) this.drawFolded(g, r, y, T0, T1);
          continue;
        }
        const tr = r.track;
        if (tr.mute) g.globalAlpha = 0.35;
        this.drawClips(g, tr, r, y, T0, T1);
        this.drawKeys(g, tr, r, y, T0, T1);
        g.globalAlpha = 1;
      }
      g.restore();
    }
    // Eingeklapptes Gerät: je Spur eine schmale Zeile, damit man sieht, wann es etwas tut
    drawFolded(g, r, y, T0, T1) {
      const tracks = this.doc.tracks.filter(t => SM.targetKey(t.target) === r.key);
      const lane = Math.max(3, Math.min(9, (r.h - 4) / Math.max(1, tracks.length)));
      tracks.forEach((tr, n) => {
        const ly = y + 2 + n * lane;
        if (ly + lane > y + r.h) return;                // sehr viele Spuren: was nicht passt, zeigt das Ausklappen
        g.globalAlpha = tr.mute ? 0.3 : 1;
        for (const s of SM.trackSpans(tr)) {
          if (s.t0 > T1 || s.t1 < T0) continue;
          const a = this.x(s.t0), b = this.x(s.t1);
          if (s.clip) {
            g.fillStyle = this.clipFill(g, s.clip, tr, a, b);
            g.fillRect(a, ly, Math.max(2, b - a), lane - 1);
          } else {
            g.fillStyle = r.color + '77';
            g.fillRect(a, ly, Math.max(2, b - a), lane - 1);
            g.fillStyle = '#f2f4fa';
            for (const k of s.keys) if (k.t >= T0 && k.t <= T1) g.fillRect(this.x(k.t) - 0.5, ly, 1.5, lane - 1);
          }
        }
      });
      g.globalAlpha = 1;
    }
    drawClips(g, tr, r, y, T0, T1) {
      for (const c of tr.clips) {
        if (c.t > T1) break;
        if (c.t + c.d < T0) continue;
        const a = this.x(c.t), b = this.x(c.t + c.d);
        g.fillStyle = this.clipFill(g, c, tr, a, b); this.round(g, a, y + 3, b - a, r.h - 7, 4); g.fill();
        g.fillStyle = r.color; g.fillRect(a + 2, y + 3, Math.max(0, b - a - 4), 2);   // oben: Farbe des Geraets
        this.fades(g, a, b, y + 3, r.h - 7, (c.p || {}).fade_in, (c.p || {}).fade_out);
        g.strokeStyle = this.sel.has(c.id) ? '#ffb35c' : '#000a'; g.lineWidth = this.sel.has(c.id) ? 2 : 1;
        this.round(g, a, y + 3, b - a, r.h - 7, 4); g.stroke();
        if (b - a > 26) {
          const moving = c.pattern === 'laser' && SWEEP.some(k => (c.p || {})[k + '_to'] !== undefined && c.p[k + '_to'] !== c.p[k]);
          const txt = this.fit_(g, (GLYPH[c.pattern] ? GLYPH[c.pattern] + ' ' : '') + (moving ? '↗ ' : '') + ((c.pattern === 'panel_scene' && (c.p || {}).panel_scene) || c.label || this.o.patternLabel(c.pattern)), b - a - 10);
          const tx = Math.max(a, this.hw) + 5, ty = y + r.h / 2 + 1;
          g.lineWidth = 3; g.strokeStyle = '#000c'; g.lineJoin = 'round'; g.strokeText(txt, tx, ty);    // lesbar auf jedem Verlauf
          g.fillStyle = '#fff'; g.fillText(txt, tx, ty);
        }
      }
    }
    // Fuellung eines Clips: Dimmer schwarz-weiss nach seiner Form, Farben bunt, Bewegung blaugruen
    clipFill(g, c, tr, a, b) {
      const gr = g.createLinearGradient(a, 0, Math.max(a + 1, b), 0), p = c.p || {}, kind = SM.kindOf(tr.attr);
      if (kind === 'color') {
        if (c.pattern === 'solid_color') {
          gr.addColorStop(0, p.color_a || '#ff0000'); gr.addColorStop(1, p.color_a || '#ff0000');
        } else if (c.pattern === 'rgb_fade') {
          gr.addColorStop(0, p.color_a || '#ff0000'); gr.addColorStop(1, p.color_b || '#0000ff');
        } else if (c.pattern === 'color_change' || c.pattern === 'red_blue') {
          const n = Math.max(1, Math.min(8, Math.round(SM.clipCycles(c, this.doc))));
          const A = p.color_a || '#ff0000', B = p.color_b || '#0000ff';
          for (let i = 0; i < n * 2; i++) {
            const col = i % 2 ? B : A;
            gr.addColorStop(i / (n * 2), col); gr.addColorStop((i + 1) / (n * 2), col);
          }
        } else {
          RAINBOW.forEach((col, i) => gr.addColorStop(i / (RAINBOW.length - 1), col));
        }
        return gr;
      }
      if (kind === 'laser') {
        const cols = { rot: ['#ff2020', '#5a0a0a'], gruen: ['#20ff50', '#0a4a18'], blau: ['#2060ff', '#0a1a5a'] }[p.laser_color] || ['#ff2020', '#20ff50'];
        const n = Math.max(2, Math.min(24, Math.round((b - a) / 14)));
        for (let i = 0; i < n; i++) {
          gr.addColorStop(i / n, cols[i % 2]); gr.addColorStop((i + 1) / n, cols[i % 2]);
        }
        return gr;
      }
      if (kind === 'panel') {
        gr.addColorStop(0, '#5a3fb0'); gr.addColorStop(1, '#7d5fd8');
        return gr;
      }
      if (kind === 'nano_fx') {
        gr.addColorStop(0, '#7a3fd0'); gr.addColorStop(0.5, '#e0508a'); gr.addColorStop(1, '#3fa0d0');
        return gr;
      }
      if (kind === 'fog') {
        gr.addColorStop(0, '#d8dde4'); gr.addColorStop(1, '#6d757e');
        return gr;
      }
      if (kind === 'move') {
        gr.addColorStop(0, '#0f6a78'); gr.addColorStop(0.5, '#1d9aa8'); gr.addColorStop(1, '#0f6a78');
        return gr;
      }
      // Schwarz-weiss nach der Form des Musters, begrenzt, damit es bei vielen Zyklen nicht zu fein wird
      const lo = p.start === undefined ? 0 : p.start, hi = p.end === undefined ? 255 : p.end, k = p.intensity === undefined ? 1 : p.intensity;
      const tint = tr.attr === 'dimmer' ? [1, 1, 1] : [0.6, 0.75, 1];         // andere Kanaele leicht blaeulich
      const col = u => { const v = lo + (hi - lo) * u * k; return 'rgb(' + tint.map(m => Math.round(v * m)).join(',') + ')'; };
      const cyc = Math.max(1, Math.min(SM.clipCycles(c, this.doc), (b - a) / 8, 24));
      const hard = c.pattern === 'blink' || c.pattern === 'strobe' || c.pattern === 'chase';
      const n = Math.ceil(cyc), steps = hard ? 1 : 8;
      for (let i = 0; i < n; i++) {
        const x0 = i / cyc, x1 = (i + 1) / cyc;
        if (x0 >= 1) break;
        if (hard) {
          const on = c.pattern === 'chase' ? 0.35 : (p.duty === undefined ? 0.5 : p.duty), xm = x0 + (x1 - x0) * on;
          gr.addColorStop(x0, col(1)); gr.addColorStop(Math.min(1, xm), col(1));
          gr.addColorStop(Math.min(1, xm), col(0)); gr.addColorStop(Math.min(1, x1), col(0));
        } else {
          for (let s = 0; s <= steps; s++) {
            const pos = x0 + (x1 - x0) * s / steps;
            if (pos <= 1) gr.addColorStop(pos, col(SM.shapeAt(c.pattern, s / steps * 0.999, p)));
          }
        }
      }
      return gr;
    }
    drawKeys(g, tr, r, y, T0, T1) {
      const K = tr.keys;
      if (!K.length) return;
      const kind = SM.kindOf(tr.attr), W = this.w, hw = this.hw;
      if (this.o.stepped(tr)) {                  // feste Stufen: Baender mit Namen statt einer Kurve
        for (let i = 0; i < K.length; i++) {
          const a = K[i], b = K[i + 1], xa = i === 0 ? hw : this.x(a.t), xb = b ? this.x(b.t) : W;
          if (xb < hw || xa > W) continue;
          g.fillStyle = i % 2 ? r.color + '44' : r.color + '66';
          g.fillRect(xa, y + 4, xb - xa, r.h - 9);
          const lx = Math.max(this.x(a.t), hw) + 10;   // Name rechts vom Keyframe, auch beim ersten
          if (xb - lx > 24) {
            g.fillStyle = '#e8eaf2';
            g.fillText(this.fit_(g, this.o.stepLabel(tr, a.v), xb - lx - 8), lx, y + r.h / 2);
          }
        }
        for (const k of K) {
          if (k.t < T0 - 1 || k.t > T1 + 1) continue;
          const x = this.x(k.t), yy = y + r.h / 2, s = this.sel.has(k.id) ? 6.5 : 5;
          g.fillStyle = this.sel.has(k.id) ? '#ffb35c' : '#f2f4fa';
          g.strokeStyle = '#0b0c12'; g.lineWidth = 1;
          g.beginPath(); g.moveTo(x, yy - s); g.lineTo(x + s, yy); g.lineTo(x, yy + s); g.lineTo(x - s, yy); g.closePath(); g.fill(); g.stroke();
        }
        return;
      }
      if (kind === 'color') {
        // Farbband zwischen den Keyframes
        for (let i = 0; i < K.length; i++) {
          const a = K[i], b = K[i + 1];
          const xa = i === 0 ? hw : this.x(a.t), xb = b ? this.x(b.t) : W;
          if (xb < hw || xa > W) continue;
          const col = v => SM.colorToHex(v);
          if (b && a.e !== 'constant') {
            const gr = g.createLinearGradient(xa, 0, xb, 0);
            gr.addColorStop(0, col(a.v)); gr.addColorStop(1, col(b.v));
            g.fillStyle = gr;
          } else g.fillStyle = col(a.v);
          g.fillRect(xa, y + r.h - 9, xb - xa, 5);
        }
      } else if (kind === 'scalar') {
        g.strokeStyle = r.color; g.lineWidth = 1.5; g.beginPath();
        const yv = v => this.vy(r, v / 255);
        g.moveTo(hw, yv(K[0].v));
        let started = false;
        for (let i = 0; i < K.length; i++) {
          const a = K[i], b = K[i + 1], xa = this.x(a.t);
          if (b && this.x(b.t) < hw) continue;
          if (!started) { g.moveTo(Math.max(hw, i ? xa : hw), yv(a.v)); started = true; }
          if (i === 0) g.lineTo(xa, yv(a.v));
          if (xa > W) break;
          if (!b) { g.lineTo(W, yv(a.v)); break; }
          const xb = this.x(b.t);
          if (a.e === 'constant') { g.lineTo(xb, yv(a.v)); g.lineTo(xb, yv(b.v)); }
          else if (a.e === 'linear') g.lineTo(xb, yv(b.v));
          else for (let s = 1; s <= 12; s++) { const u = s / 12; g.lineTo(xa + (xb - xa) * u, yv(a.v + (b.v - a.v) * SM.ease(a.e, u))); }
        }
        g.stroke();
      }
      for (const k of K) {
        if (k.t < T0 - 1 || k.t > T1 + 1) continue;
        const x = this.x(k.t), yy = kind === 'scalar' ? this.vy(r, k.v / 255) : y + r.h / 2, s = this.sel.has(k.id) ? 6.5 : 5;
        g.fillStyle = this.sel.has(k.id) ? '#ffb35c' : kind === 'color' ? SM.colorToHex(k.v) : '#f2f4fa';
        g.strokeStyle = '#0b0c12'; g.lineWidth = 1;
        g.beginPath(); g.moveTo(x, yy - s); g.lineTo(x + s, yy); g.lineTo(x, yy + s); g.lineTo(x - s, yy); g.closePath(); g.fill(); g.stroke();
      }
    }
    drawOver() {
      const g = this.octx;
      g.clearRect(0, 0, this.w, this.h);
      if (!this.doc) return;
      const x = this.x(this.linePos === undefined ? this.pos : this.linePos);
      if (x >= this.hw && x <= this.w) {
        g.fillStyle = '#ff3b30'; g.fillRect(x - 0.75, 0, 1.5, this.h);
        g.beginPath(); g.moveTo(x - 6, 0); g.lineTo(x + 6, 0); g.lineTo(x, 9); g.closePath(); g.fill();
      }
      const d = this.drag;
      if (d && d.mode === 'reorder' && d.moved && d.dropY !== undefined) {
        const ly = this.top() - this.sy + d.dropY;
        g.fillStyle = '#ffb35c'; g.fillRect(0, ly - 1.5, this.w, 3);
      }
      if (d && d.mode === 'rubber') {
        g.strokeStyle = '#ffb35c'; g.fillStyle = '#ffb35c22'; g.lineWidth = 1;
        g.fillRect(d.x0, d.y0, d.x1 - d.x0, d.y1 - d.y0); g.strokeRect(d.x0, d.y0, d.x1 - d.x0, d.y1 - d.y0);
      }
      if (this.snapX !== undefined) { g.fillStyle = '#ffb35c88'; g.fillRect(this.snapX, RULER, 1, this.h - RULER); }
      if (this.edgeMark && !this.drag) { g.fillStyle = '#ffb35c'; g.fillRect(this.edgeMark.x - 2, this.edgeMark.y, 4, this.edgeMark.h); }
    }

    // ---- Bedienung ---------------------------------------------------------------------------------
    local(e) { const r = this.host.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
    snap(t) { const m = this.markAt(t); return m !== null ? m : SM.snap(t, this.doc, this.doc.grid); }
    markAt(t) {                                  // naechster Cue oder Abschnittsrand in Reichweite; Raster aus = nirgends einrasten
      const m = this.marks();
      if (!m || !SM.gridStep(this.doc, this.doc.grid)) return null;
      let best = null, bd = MARK_SNAP_PX / this.pxs;
      for (const c of [...m.cu, ...m.se.flatMap(s => [s[1], s[2]])]) if (Math.abs(c - t) <= bd) { bd = Math.abs(c - t); best = c; }
      return best;
    }
    select(id, add) {
      if (!add) this.sel.clear();
      if (id) { if (add && this.sel.has(id)) this.sel.delete(id); else this.sel.add(id); }
      this.o.onSelect(); this.need = true;
    }
    down(e) {
      if (!this.doc) return;
      const [x, y] = this.local(e);
      this.host.setPointerCapture(e.pointerId);
      this.ptr.set(e.pointerId, [x, y]);
      if (this.ptr.size === 2) {                      // zwei Finger: zoomen und schieben
        const [a, b] = [...this.ptr.values()];
        this.drag = { mode: 'pinch', dist: Math.abs(a[0] - b[0]) || 1, cx: (a[0] + b[0]) / 2, cy: (a[1] + b[1]) / 2 };
        return;
      }
      const add = e.shiftKey || e.ctrlKey || e.metaKey || this.multi;
      const h = this.hit(x, y);
      const base = { x0: x, y0: y, x1: x, y1: y, moved: false, t0: this.t(x), h, add, pointer: e.pointerType };
      if (h.zone === 'ruler' && y < RULER) {          // Lineal: Antippen springt, Ziehen setzt den Loop, seine Ränder und er selbst lassen sich ziehen
        const L = this.loop, edge = L ? SM.clipEdge(x, this.x(L.t0), this.x(L.t1)) : '';
        const inside = L && x > this.x(L.t0) && x < this.x(L.t1);
        const mode = edge === 'l' ? 'loopL' : edge === 'r' ? 'loopR' : inside ? 'loopMove' : 'loopNew';
        this.drag = { ...base, mode, loop0: L ? { ...L } : null };
        return;
      }
      if (h.zone === 'ruler') { this.drag = { ...base, mode: 'seek' }; this.o.onSeek(SM.clamp(this.t(x), 0, this.doc.duration)); return; }
      if (h.zone === 'corner' && h.btn === 'fold') { this.foldAll(); return; }
      if (h.zone === 'corner' && h.btn === 'stems') { this.showStems = this.showStems === false; if (this.o.onStems) this.o.onStems(this.showStems); this.clampView(); this.need = true; return; }
      if (h.zone === 'head') {
        if (h.btn === 'del') { this.o.onDeleteTarget(h.row.target); return; }
        this.drag = { ...base, mode: 'reorder', key: h.row.key };     // Antippen klappt, Ziehen sortiert um (siehe up)
        return;
      }
      if (h.zone === 'trackhead') {
        if (h.btn === 'del') { this.o.onDeleteTrack(h.row.track); return; }
        if (h.btn === 'mute') { this.o.begin(); h.row.track.mute = !h.row.track.mute; this.o.commit(); return; }
        this.selTrack = h.row.track.id; this.sel.clear(); this.o.onSelect(); this.need = true;
        this.drag = { ...base, mode: 'scrollY', sy0: this.sy };
        return;
      }
      if (h.zone === 'key' || h.zone === 'clip' || h.zone === 'scene') {
        if (h.track) this.selTrack = h.track.id;
        if (!this.sel.has(h.id)) this.select(h.id, add); else if (add) { base.toggle = h.id; }
        const mode = h.edge === 'r' ? 'resizeR' : h.edge === 'l' ? 'resizeL' : 'moveEv';
        if (e.pointerType !== 'touch') this.host.style.cursor = h.edge ? 'ew-resize' : h.zone === 'key' ? 'move' : 'grabbing';
        this.drag = { ...base, mode, ev: h.ev, evT: h.ev.t, evD: h.ev.d, evV: h.ev.v, row: h.row, type: h.zone };
        return;
      }
      if (h.zone === 'lane') this.selTrack = h.track.id;
      if (e.pointerType === 'mouse' || this.multi) this.drag = { ...base, mode: 'rubber' };
      else this.drag = { ...base, mode: 'pan', t00: this.t0, sy0: this.sy };
      this.need = true;
    }
    // Maus über der Timeline: der Zeiger zeigt, was Ziehen hier tut, wie im Videoschnitt
    hover(e) {
      if (!this.doc || e.pointerType === 'touch') return;
      const [x, y] = this.local(e), h = this.hit(x, y);
      const onClip = h.zone === 'clip' || h.zone === 'scene';
      if (h.zone === 'ruler' && y < RULER) {
        const L = this.loop, cl = L && SM.clipEdge(x, this.x(L.t0), this.x(L.t1));
        const c2 = cl ? 'ew-resize' : L && x > this.x(L.t0) && x < this.x(L.t1) ? 'grab' : 'text';
        if (this.host.style.cursor !== c2) this.host.style.cursor = c2;
        this.edgeMark = null;
        return;
      }
      const cur = onClip && h.edge ? 'ew-resize' : onClip ? 'grab' : h.zone === 'key' ? 'move' : h.zone === 'ruler' ? 'col-resize'
        : h.zone === 'head' ? (h.btn ? 'pointer' : 'grab') : h.zone === 'trackhead' || (h.zone === 'corner' && h.btn) ? 'pointer' : 'default';
      if (this.host.style.cursor !== cur) this.host.style.cursor = cur;
      this.edgeMark = null;
      if (onClip && h.edge) {
        const X = this.x(h.edge === 'r' ? h.ev.t + h.ev.d : h.ev.t);
        this.edgeMark = h.zone === 'scene' ? { x: X, y: this.wb() + 3, h: SCENE - 6 } : { x: X, y: this.top() - this.sy + h.row.y + 3, h: h.row.h - 7 };
      }
    }
    move(e) {
      if (!this.ptr.has(e.pointerId)) { this.hover(e); return; }
      const [x, y] = this.local(e);
      this.ptr.set(e.pointerId, [x, y]);
      const d = this.drag;
      if (!d) return;
      if (d.mode === 'pinch' && this.ptr.size >= 2) {
        this.userView = true;
        const [a, b] = [...this.ptr.values()];
        const dist = Math.abs(a[0] - b[0]) || 1, cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2;
        this.zoom(dist / d.dist, cx);
        this.t0 -= (cx - d.cx) / this.pxs; this.sy -= cy - d.cy;
        d.dist = dist; d.cx = cx; d.cy = cy;
        this.clampView(); this.need = true;
        return;
      }
      if (!d.moved && Math.hypot(x - d.x0, y - d.y0) < 4) return;
      const first = !d.moved;
      d.moved = true; d.x1 = x; d.y1 = y;
      const dtRaw = this.t(x) - d.t0;
      switch (d.mode) {
        case 'seek': this.o.onSeek(SM.clamp(this.t(x), 0, this.doc.duration)); break;
        case 'loopNew': case 'loopL': case 'loopR': case 'loopMove': {
          const min = Math.max(0.1, SM.gridStep(this.doc, this.doc.grid)), dur = this.doc.duration, t = SM.clamp(this.snap(this.t(x)), 0, dur);
          const L0 = d.loop0;
          let t0, t1;
          if (d.mode === 'loopNew') { const a = SM.clamp(this.snap(d.t0), 0, dur); t0 = Math.min(a, t); t1 = Math.max(a, t); }
          else if (d.mode === 'loopL') { t0 = Math.min(t, L0.t1 - min); t1 = L0.t1; }
          else if (d.mode === 'loopR') { t0 = L0.t0; t1 = Math.max(t, L0.t0 + min); }
          else {
            const len = L0.t1 - L0.t0;
            t0 = SM.clamp(this.snap(L0.t0 + dtRaw), 0, Math.max(0, dur - len)); t1 = t0 + len;
          }
          if (t1 - t0 >= min) { this.loop = { t0, t1, on: d.mode === 'loopNew' ? true : L0.on }; this.o.onLoop(this.loop); this.need = true; }
          break;
        }
        case 'reorder': {
          if (y < this.top() + 20) this.sy -= 8; else if (y > this.h - 20) this.sy += 8;   // am Rand mitlaufen
          this.clampView();
          const yy = y - this.top() + this.sy;
          const heads = this.rows.filter(r => r.type === 'head');
          let before = null, dy = this.rowsH;
          for (let i = 0; i < heads.length; i++) {
            const end = i + 1 < heads.length ? heads[i + 1].y : this.rowsH;
            if (yy < (heads[i].y + end) / 2) { before = heads[i].key; dy = heads[i].y; break; }
          }
          d.before = before; d.dropY = dy;
          if (e.pointerType !== 'touch') this.host.style.cursor = 'grabbing';
          this.need = true; break;
        }
        case 'pan':
          this.userView = true;
          this.t0 = d.t00 - (x - d.x0) / this.pxs; this.sy = d.sy0 - (y - d.y0);
          this.clampView(); this.need = true; break;
        case 'scrollY':
          this.sy = d.sy0 - (y - d.y0); this.clampView(); this.need = true; break;
        case 'moveEv': {
          if (first) this.o.begin();
          let target = this.snap(d.evT + dtRaw);
          if (d.ev.d && this.markAt(d.evT + dtRaw) === null) {   // auch mit dem Ende an einen Cue
            const e = this.markAt(d.evT + dtRaw + d.ev.d);
            if (e !== null) target = e - d.ev.d;
          }
          SM.moveEvents(this.doc, this.sel, target - d.ev.t);
          if (d.type === 'key' && SM.kindOf(d.h.track.attr) === 'scalar' && !this.o.stepped(d.h.track) && this.sel.size === 1 && !e.altKey) {
            d.ev.v = Math.round(this.uy(d.row, y) * 255);
          }
          this.snapX = this.x(d.ev.t);
          this.o.onLive(); this.need = true; break;
        }
        case 'resizeR': {
          if (first) this.o.begin();
          d.ev.d = SM.clamp(this.snap(d.evT + d.evD + dtRaw) - d.ev.t, this.minLen(), this.maxLen(d));
          this.snapX = this.x(d.ev.t + d.ev.d);
          this.o.onLive(); this.need = true; break;
        }
        case 'resizeL': {
          if (first) this.o.begin();
          const end = d.evT + d.evD;
          const st = SM.clamp(this.snap(d.evT + dtRaw), Math.max(0, end - this.maxLen(d)), end - this.minLen());
          d.ev.t = st; d.ev.d = end - st;
          this.snapX = this.x(st);
          this.o.onLive(); this.need = true; break;
        }
      }
    }
    up(e, cancel) {
      if (!this.ptr.has(e.pointerId)) return;
      const [x, y] = this.local(e);
      this.ptr.delete(e.pointerId);
      const d = this.drag;
      if (this.ptr.size) { if (d && d.mode === 'pinch') this.drag = null; return; }
      this.drag = null; this.snapX = undefined; this.edgeMark = null;
      if (e.pointerType !== 'touch') this.host.style.cursor = '';
      if (!d || cancel) { this.need = true; return; }
      if (d.mode === 'rubber' && d.moved) { this.finishRubber(d); return; }
      if (d.mode.startsWith('loop') && !d.moved) { this.userView = false; this.o.onSeek(SM.clamp(this.t(x), 0, this.doc.duration)); return; }
      if (d.mode === 'loopNew') { this.o.onLoopNew(); return; }
      if (d.mode === 'reorder') {
        if (d.moved) {
          const trial = { tracks: this.doc.tracks.slice() };           // erst prüfen: ohne Änderung kein Undo-Schritt
          if (d.dropY !== undefined && SM.moveTarget(trial, d.key, d.before)) {
            this.o.begin();
            SM.moveTarget(this.doc, d.key, d.before);
            this.o.commit();
          }
        } else {
          if (this.collapsed.has(d.key)) this.collapsed.delete(d.key); else this.collapsed.add(d.key);
          this.o.onFold([...this.collapsed]);
          this.rebuild();
        }
        this.need = true;
        return;
      }
      if (['moveEv', 'resizeR', 'resizeL'].includes(d.mode) && d.moved) { SM.resort(this.doc); this.o.commit(); return; }
      if (d.toggle && !d.moved) this.select(d.toggle, true);
      if (!d.moved) this.tap(x, y, d);
      this.need = true;
    }
    minLen() { return Math.max(0.025, SM.gridStep(this.doc, this.doc.grid)); }   // nie kürzer als ein Rasterschritt
    maxLen(d) { return d.h.track && d.h.track.attr === 'fog' ? 10 : Infinity; }   // Nebelschub: höchstens 10 s
    tap(x, y, d) {
      const h = d.h, now = performance.now();
      const dbl = this.lastTap && now - this.lastTap.t < 380 && Math.hypot(this.lastTap.x - x, this.lastTap.y - y) < 18;
      this.lastTap = dbl ? null : { t: now, x, y };
      if (dbl && h.zone === 'headlane' && this.collapsed.has(h.row.key)) {   // doppelt auf die Mini-Spuren: ausklappen
        this.collapsed.delete(h.row.key);
        this.o.onFold([...this.collapsed]);
        this.rebuild();
        return;
      }
      if (h.zone === 'lane' || h.zone === 'headlane' || h.zone === 'sceneempty' || h.zone === 'empty') {
        if (dbl && h.zone === 'lane' && h.row.panel) {
          this.o.onAddPanelScene(this.snap(this.t(x)));
        } else if (dbl && h.zone === 'lane' && SM.clipsOnly(h.track.attr)) {
          SM.toast('Auf dieser Spur gibt es nur Clips: unter Muster auf die Spur ziehen');
        } else if (dbl && h.zone === 'lane') {
          const tr = h.track, kind = SM.kindOf(tr.attr);
          this.o.begin();
          const jump = this.o.stepped(tr);
          const v = jump ? this.o.newStepValue(tr, this.t(x))
            : kind === 'scalar' ? Math.round(this.uy(h.row, y) * 255) : (SM.keyValueAt(tr, this.t(x)) || SM.defaultValue(kind));
          const k = SM.addKey(this.doc, tr, this.snap(this.t(x)), v, jump ? 'constant' : 'linear');
          this.sel = new Set([k.id]);
          this.o.commit(); this.o.onSelect();
        } else if (!d.add) this.select(null);
      }
    }
    finishRubber(d) {
      const x0 = Math.min(d.x0, d.x1), x1 = Math.max(d.x0, d.x1), y0 = Math.min(d.y0, d.y1), y1 = Math.max(d.y0, d.y1);
      if (!d.add) this.sel.clear();
      const top = this.top(), t0 = this.t(x0), t1 = this.t(x1);
      for (const r of this.rows) {
        if (r.type !== 'track') continue;
        const ry = top - this.sy + r.y;
        if (ry + r.h < y0 || ry > y1) continue;
        for (const k of r.track.keys) if (k.t >= t0 && k.t <= t1) this.sel.add(k.id);
        for (const c of r.track.clips) if (c.t + c.d >= t0 && c.t <= t1) this.sel.add(c.id);
      }
      if (y0 < top && y1 > this.wb()) for (const c of this.doc.scene_clips) if (c.t + c.d >= t0 && c.t <= t1) this.sel.add(c.id);
      this.o.onSelect(); this.need = true;
    }
    wheel(e) {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey || e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) this.userView = true;
      const [x] = this.local(e);
      if (e.ctrlKey || e.metaKey) this.zoom(Math.exp(-e.deltaY * 0.004), Math.max(x, this.hw));
      else if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) { this.t0 += (e.deltaX || e.deltaY) / this.pxs; this.clampView(); this.need = true; }
      else { this.sy += e.deltaY; this.clampView(); this.need = true; }
    }
    // Ziel beim Ablegen aus der linken Leiste
    dropInfo(cx, cy) {
      const r = this.host.getBoundingClientRect(), x = cx - r.left, y = cy - r.top;
      if (x < 0 || y < 0 || x > r.width || y > r.height) return null;
      const t = x > this.hw ? this.snap(this.t(x)) : this.snap(this.pos);
      const inScene = y >= this.wb() && y < this.wb() + SCENE;
      return { t, row: y >= this.wb() + SCENE ? this.rowAt(y) : null, inScene };
    }
  };
})();
