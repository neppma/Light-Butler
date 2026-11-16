// room.js - Raumplan: Geraete im Grundriss platzieren (Seite /raum). Nur ein Plan, aufs Licht wirkt er nicht.
(function () {
  'use strict';
  const SM = window.SM;
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const COLOR = { bars: '#ff7a59', wash: '#7d8cff', spot: '#cfd3e6', locked: '#ff5fa2', fx: '#c58bff', uv: '#a066ff', ambient: '#2fd4c6', nano: '#3ddc6a' };
  const BAND = '#ffc83d';
  let room = null, devs = [], sel = null, dirty = false, drag = null;

  const byName = n => devs.find(d => d.name === n.split('#')[0]);
  const color = k => { const d = byName(k); return d && d.line && d.group === 'ambient' && k.startsWith('effektband') ? BAND : COLOR[(d || {}).group] || '#aab'; };
  const part = k => k.includes('#') ? ' (' + k.split('#')[1] + ')' : '';
  const label = k => { const d = byName(k); return d ? (d.nr ? d.nr + ' · ' : '') + d.label + part(k) : k; };
  const short = k => { const d = byName(k); return d ? (d.short || d.label) + part(k) : k; };
  const snap = v => $('snap').checked ? Math.round(v * 10) / 10 : Math.round(v * 1000) / 1000;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function setDirty(on) { dirty = on; $('dirty').textContent = on ? ' •' : ''; }
  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  function draw() {
    const svg = $('plan'), W = room.w, H = room.h, m = 0.5;
    svg.setAttribute('viewBox', (-m) + ' ' + (-m) + ' ' + (W + 2 * m) + ' ' + (H + 2 * m));
    // Safari (iPad) rechnet die Hoehe eines SVG ohne Groesse nicht aus dem viewBox: 150 px, der Plan wird ein Streifen
    svg.style.aspectRatio = (W + 2 * m) + ' / ' + (H + 2 * m);
    svg.innerHTML = '';
    el('rect', { x: 0, y: 0, width: W, height: H, fill: '#12131c', stroke: '#5a5f76', 'stroke-width': 0.05 }, svg);
    for (let x = 0.5; x < W; x += 0.5) el('line', { x1: x, y1: 0, x2: x, y2: H, stroke: x % 1 ? '#1a1c28' : '#24273a', 'stroke-width': 0.012 }, svg);
    for (let y = 0.5; y < H; y += 0.5) el('line', { x1: 0, y1: y, x2: W, y2: y, stroke: y % 1 ? '#1a1c28' : '#24273a', 'stroke-width': 0.012 }, svg);
    const t1 = el('text', { x: W / 2, y: -0.15, fill: '#889', 'font-size': 0.2, 'text-anchor': 'middle' }, svg); t1.textContent = W + ' m';
    const t2 = el('text', { x: -0.15, y: H / 2, fill: '#889', 'font-size': 0.2, 'text-anchor': 'end', 'dominant-baseline': 'middle' }, svg); t2.textContent = H + ' m';
    const keys = Object.keys(room.items).sort((a, b) => (room.items[b].len > 0) - (room.items[a].len > 0));   // Streifen unten, Punkte obenauf
    for (const k of keys) {
      const it = room.items[k], c = color(k), on = k === sel;
      const g = el('g', { transform: 'translate(' + it.x + ' ' + it.y + ') rotate(' + it.rot + ')', style: 'cursor:grab' }, svg);
      g.dataset.k = k;
      if (it.len > 0) {
        el('line', { x1: -it.len / 2, y1: 0, x2: it.len / 2, y2: 0, stroke: c, 'stroke-width': on ? 0.12 : 0.08, 'stroke-linecap': 'round' }, g);
        el('line', { x1: -it.len / 2, y1: 0, x2: it.len / 2, y2: 0, stroke: 'transparent', 'stroke-width': 0.22 }, g);
        el('circle', { cx: 0, cy: 0, r: 0.1, fill: c, stroke: on ? '#fff' : 'none', 'stroke-width': 0.03 }, g);
      } else {
        el('line', { x1: 0, y1: 0, x2: 0.32, y2: 0, stroke: c, 'stroke-width': 0.03, opacity: 0.8 }, g);   // Blickrichtung
        el('circle', { cx: 0, cy: 0, r: on ? 0.17 : 0.14, fill: c, stroke: on ? '#fff' : '#0d0e16', 'stroke-width': 0.03 }, g);
        el('circle', { cx: 0, cy: 0, r: 0.35, fill: 'transparent' }, g);
      }
      const ty = it.len > 0 ? (it.y < 0.4 ? 0.3 : -0.14) : (it.y < 0.4 ? 0.36 : -0.22);   // an der oberen Wand darunter
      const flat = it.len > 0 && it.rot % 180 === 0;             // waagrechter Streifen: Name am linken Ende, die Mitte bleibt frei
      const anchor = flat ? 'start' : it.len > 0 ? 'middle' : it.x < 0.7 ? 'start' : it.x > W - 0.7 ? 'end' : 'middle';
      const ax = flat ? it.x - it.len / 2 + 0.6 : anchor === 'start' ? it.x - 0.15 : anchor === 'end' ? it.x + 0.15 : it.x;
      const tx = el('text', { x: ax, y: it.y + ty, fill: on ? '#fff' : '#cfd3e6', 'font-size': 0.15, 'text-anchor': anchor, 'pointer-events': 'none' }, svg);
      tx.textContent = short(k);
    }
    drawFree();
    drawSel();
  }

  function drawFree() {
    const box = $('free');
    box.innerHTML = '';
    const missing = devs.filter(d => !room.items[d.name]);
    if (!missing.length) { box.innerHTML = '<p class="dim">Alle Geräte stehen im Plan.</p>'; return; }
    for (const d of missing) {
      const b = document.createElement('button');
      b.innerHTML = '<span class="dot"></span>';
      b.firstChild.style.background = COLOR[d.group] || '#aab';
      b.appendChild(document.createTextNode(label(d.name)));
      b.onclick = () => { room.items[d.name] = { x: snap(room.w / 2), y: snap(room.h / 2), rot: 0, len: d.line ? 2 : 0 }; sel = d.name; setDirty(true); draw(); };
      box.appendChild(b);
    }
  }

  function num(lab, val, step, set) {
    const r = document.createElement('div');
    r.className = 'row';
    r.innerHTML = '<label></label><input type="number">';
    r.firstChild.textContent = lab;
    const i = r.lastChild;
    i.step = step; i.value = val;
    i.onchange = () => { const v = parseFloat(i.value); if (isFinite(v)) { set(v); setDirty(true); draw(); } };
    return r;
  }
  function btn(text, fn, title) {
    const b = document.createElement('button');
    b.textContent = text;
    if (title) b.title = title;
    b.onclick = () => { fn(); setDirty(true); draw(); };
    return b;
  }

  function drawSel() {
    const B = $('sel');
    if (!sel || !room.items[sel]) {
      B.innerHTML = '<h3>Gerät</h3><p class="dim">Ein Gerät im Plan antippen und ziehen. Fehlende Geräte unten antippen, sie kommen in die Mitte.</p>';
      return;
    }
    const it = room.items[sel], d = byName(sel);
    B.innerHTML = '<h3></h3>';
    B.firstChild.textContent = label(sel);
    B.appendChild(num('X (m von links)', it.x, 0.1, v => { it.x = clamp(v, 0, room.w); }));
    B.appendChild(num('Y (m von oben)', it.y, 0.1, v => { it.y = clamp(v, 0, room.h); }));
    B.appendChild(num(it.len > 0 ? 'Drehung (Grad)' : 'Blickrichtung (Grad)', it.rot, 15, v => { it.rot = ((v % 360) + 360) % 360; }));
    const rr = document.createElement('div');
    rr.className = 'row';
    rr.appendChild(btn('↺ 15°', () => { it.rot = (it.rot + 345) % 360; }));
    rr.appendChild(btn('↻ 15°', () => { it.rot = (it.rot + 15) % 360; }));
    rr.appendChild(btn('90°', () => { it.rot = (it.rot + 90) % 360; }, 'Um 90 Grad drehen'));
    B.appendChild(rr);
    B.appendChild(num('Länge (m, 0 = Punkt)', it.len, 0.1, v => { it.len = clamp(v, 0, Math.max(room.w, room.h)); }));
    const r2 = document.createElement('div');
    r2.className = 'row';
    if (d && d.line && !sel.includes('#')) {
      r2.appendChild(btn('+ Stück', () => {
        let n = 2;
        while (room.items[d.name + '#' + n] && n < 9) n++;
        if (n > 9) return;
        room.items[d.name + '#' + n] = { x: it.x, y: clamp(it.y + 0.5, 0, room.h), rot: it.rot, len: it.len };
        sel = d.name + '#' + n;
      }, 'Ein weiteres Stück desselben Streifens, zum Beispiel das zweite Segment des Effektbands'));
    }
    r2.appendChild(btn('Aus dem Plan', () => { delete room.items[sel]; sel = null; }));
    B.appendChild(r2);
  }

  function pt(e) {
    const svg = $('plan'), p = svg.createSVGPoint();
    p.x = e.clientX; p.y = e.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  }

  function bind() {
    const svg = $('plan');
    svg.addEventListener('pointerdown', e => {
      const g = e.target.closest('g[data-k]');
      if (!g) { sel = null; draw(); return; }
      const k = g.dataset.k, p = pt(e), it = room.items[k];
      sel = k;
      drag = { k, dx: it.x - p.x, dy: it.y - p.y, moved: false };
      svg.setPointerCapture(e.pointerId);
      draw();
    });
    svg.addEventListener('pointermove', e => {
      if (!drag) return;
      const p = pt(e), it = room.items[drag.k];
      it.x = clamp(snap(p.x + drag.dx), 0, room.w);
      it.y = clamp(snap(p.y + drag.dy), 0, room.h);
      drag.moved = true;
      setDirty(true);
      draw();
    });
    const end = () => { drag = null; };
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);
    $('rw').onchange = () => { room.w = clamp(parseFloat($('rw').value) || room.w, 1, 40); setDirty(true); draw(); };
    $('rh').onchange = () => { room.h = clamp(parseFloat($('rh').value) || room.h, 1, 40); setDirty(true); draw(); };
    $('bsave').onclick = save;
    $('bflipx').onclick = () => flip(true);
    $('bflipy').onclick = () => flip(false);
    window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
    document.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); save(); }
    });
  }

  // Ganzen Plan spiegeln: Positionen und Richtungen
  function flip(horiz) {
    for (const it of Object.values(room.items)) {
      if (horiz) { it.x = Math.round((room.w - it.x) * 1000) / 1000; it.rot = (540 - it.rot) % 360; }
      else { it.y = Math.round((room.h - it.y) * 1000) / 1000; it.rot = (360 - it.rot) % 360; }
    }
    setDirty(true);
    draw();
  }

  async function save() {
    try {
      const r = await SM.cmd('room_save', { room });
      room = r.room;
      setDirty(false);
      hint();
      draw();
      SM.toast('Raumplan gespeichert');
    } catch (e) { SM.toast('Nicht gespeichert: ' + e.message, 6000); }
  }

  function hint() {
    $('hint').textContent = room.guess ? 'Das ist ein erster Vorschlag aus deiner Beschreibung. Bitte die Geräte an ihren richtigen Platz ziehen und speichern.' : '';
  }

  async function main() {
    const r = await SM.cmd('room', {});
    room = r.room; devs = r.devices;
    $('rw').value = room.w; $('rh').value = room.h;
    hint();
    bind();
    draw();
  }
  main().catch(e => { $('hint').textContent = 'Raumplan nicht ladbar: ' + e.message; });
})();
