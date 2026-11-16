// debug.js - DMX-Debugger: jeder Kanal einzeln. Die Seite hält ihn am Leben (Totmann, siehe dmx_debug.py).
(function () {
  'use strict';
  const SM = window.SM, $ = id => document.getElementById(id), esc = SM.esc;
  let holding = false, holdChain = Promise.resolve();
  let armed = false, values = new Array(512).fill(0), pending = {}, timer = null, fixtures = [];

  const inputs = new Map();                 // Kanal -> [Regler, Zahl, Zeile]
  function show(s) {
    if (!s) return;
    const was = armed;
    armed = !!s.armed;
    values = s.values || values;
    $('arm').classList.toggle('on', armed);
    $('arm').textContent = armed ? 'Debug AN: ausschalten' : 'Debug einschalten';
    $('rows').classList.toggle('live', armed);
    $('hold').disabled = !armed;
    if (!armed) { holding = false; $('hold').classList.remove('on'); }
    if (was && !armed) { pending = {}; SM.toast(s.blackout ? 'BLACKOUT: Debug aus' : 'Debug aus', 3000); }
    $('st').textContent = armed ? 'An. Die Show ruht auf der DMX-Kette, oben im Panel steht DMX-DEBUG AN.' : (s.blackout ? 'Aus: BLACKOUT ist an.' : 'Aus. Die Show steuert das Licht.');
    for (const [ch, x] of inputs) {
      if (document.activeElement === x[0] || document.activeElement === x[1] || pending[ch] !== undefined) continue;
      const v = values[ch - 1] || 0;
      x[0].value = v; x[1].value = v; x[2].classList.toggle('nz', v > 0);
    }
  }
  const flush = () => {
    timer = null;
    const send = pending;
    pending = {};
    if (Object.keys(send).length) SM.cmd('debug_set', { values: send }).then(show).catch(e => SM.toast(e.message));
  };
  function setChannel(ch, v) {
    v = SM.clamp(Math.round(+v) || 0, 0, 255);
    pending[ch] = v;
    const x = inputs.get(ch);
    if (x) { x[0].value = v; x[1].value = v; x[2].classList.toggle('nz', v > 0); }
    if (!timer) timer = setTimeout(flush, 40);
  }
  // Taster: drücken = alles 0, loslassen = wieder die Regler. Der Reihe nach senden, sonst könnte ein spätes Loslassen zuerst ankommen.
  function setHold(on) {
    if (on === holding || (on && !armed)) return;
    holding = on;
    $('hold').classList.toggle('on', on);
    $('hold').textContent = on ? 'DUNKEL: loslassen = Werte zurück' : 'Kurz dunkel (halten)';
    holdChain = holdChain.then(() => SM.cmd('debug_hold', { on })).catch(e => SM.toast(e.message));
  }
  function render() {
    const R = $('rows'), sel = $('fx').value;
    R.innerHTML = '';
    inputs.clear();
    const rows = [];
    if (sel === 'all') for (let c = 1; c <= 512; c++) rows.push({ ch: c, name: 'Kanal ' + c, desc: '' });
    else {
      const f = fixtures.find(x => x.name === sel);
      for (const m of f.map) rows.push({ ch: f.address + m.ch - 1, name: m.param, desc: f.desc[m.param] || '' });
    }
    for (const r of rows) {
      const d = document.createElement('div');
      d.className = 'dr';
      d.innerHTML = '<i>' + r.ch + '</i><span>' + esc(r.name) + '</span><input type="range" min="0" max="255" step="1" value="0"><input type="number" min="0" max="255" value="0">' + (r.desc ? '<small>' + esc(r.desc) + '</small>' : '');
      const [rg, nu] = d.querySelectorAll('input');
      rg.oninput = () => setChannel(r.ch, rg.value);
      nu.onchange = () => setChannel(r.ch, nu.value);
      inputs.set(r.ch, [rg, nu, d]);
      R.appendChild(d);
    }
    show({ armed, values });
  }
  async function main() {
    const m = await SM.get('/api/sm/meta');
    fixtures = m.fixtures.filter(f => !f.target);
    const want = new URLSearchParams(location.search).get('fx') || 'laser';
    $('fx').innerHTML = fixtures.map(f => '<option value="' + esc(f.name) + '"' + (f.name === want ? ' selected' : '') + '>' + esc((f.nr ? f.nr + ' · ' : '') + f.label + ' (DMX ' + f.address + '–' + (f.address + f.channels - 1) + ')') + '</option>').join('') + '<option value="all">Alle Kanäle 1 bis 512</option>';
    $('fx').onchange = render;
    $('arm').onclick = () => SM.cmd('debug_arm', { on: !armed }).then(show).catch(e => SM.toast(e.message, 5000));
    $('zero').onclick = () => { const a = {}; for (let c = 1; c <= 512; c++) a[c] = 0; pending = {}; SM.cmd('debug_set', { values: a }).then(show).catch(e => SM.toast(e.message)); };
    const H = $('hold');
    H.addEventListener('pointerdown', e => { e.preventDefault(); try { H.setPointerCapture(e.pointerId); } catch (x) { /* schon weg */ } setHold(true); });
    for (const t of ['pointerup', 'pointercancel', 'lostpointercapture']) H.addEventListener(t, () => setHold(false));
    H.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', e => { if (e.code === 'Space' && !e.repeat && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') { e.preventDefault(); setHold(true); } });
    document.addEventListener('keyup', e => { if (e.code === 'Space') setHold(false); });
    window.addEventListener('blur', () => setHold(false));
    render();
    show(await SM.cmd('debug_state'));
    setInterval(() => { SM.cmd(armed ? 'debug_beat' : 'debug_state').then(show).catch(() => { $('st').textContent = 'Keine Verbindung: Nach 2 s schaltet der Light-Butler den Debugger aus.'; }); }, 400);
    window.addEventListener('pagehide', () => { if (armed && navigator.sendBeacon) navigator.sendBeacon('/api/sm/cmd', JSON.stringify({ op: 'debug_arm', on: false })); });
  }
  main().catch(e => SM.toast(e.message, 8000));
})();
