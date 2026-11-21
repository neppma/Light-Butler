// ofl.js - Geraetetyp aus der Open Fixture Library (open-fixture-library.org) oder aus einer Datei (.json, .qxf) uebernehmen.
// Teil des Fixture-Editors (/fixtures, "+ Fixture"). Der Licht-Rechner fragt die Datenbank nur auf Knopfdruck ab
// (/api/ofl/man, /api/ofl/fx), wandelt das Geraet um (/api/ofl/preview) und speichert es als eigenen Typ (Befehl type_import).
(function () {
  'use strict';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const GRP = { bars: 'Spider', wash: 'Wash', bar: 'Barlicht', fx: 'Effekt', uv: 'UV-Leiste', spot: 'Moving Head', ambient: 'Ambiente', locked: 'gesperrt (nie angesteuert)' };
  const ROLE = {
    dimmer: 'Helligkeit', r: 'Rot', g: 'Grün', b: 'Blau', w: 'Weiß', uv: 'UV', pan: 'Drehung', tilt: 'Neigung', pan_fine: 'Drehung fein',
    tilt_fine: 'Neigung fein', shutter: 'Shutter (offen)', strobe: 'Strobe (aus)', colorwheel: 'Farbrad', gobo: 'Gobo', gobo_rot: 'Gobo-Drehung',
    zoom: 'Zoom', focus: 'Fokus', prism: 'Prisma', pt_speed: 'Tempo Bewegung'
  };
  let man = '', list = [], cur = null, mode = 0, src = '';

  async function getJ(url, opt) {
    const r = await fetch(url, opt);
    const j = await r.json().catch(() => ({ error: 'Antwort nicht lesbar' }));
    if (!r.ok || j.error && !j.modes) throw new Error(j.error || 'Fehler');
    return j;
  }

  function role(p) {
    if (ROLE[p]) return ROLE[p];
    const m = /^(r|g|b|w|uv)(\d+)$/.exec(p);
    if (m) return ROLE[m[1]] + ' Zelle ' + m[2];
    if (/^dimmer\d+$/.test(p)) return 'Helligkeit';
    return p.indexOf('x_') === 0 ? 'nicht benutzt' : '';
  }

  function preview(box) {
    const pv = box.querySelector('#ofl_pv');
    if (!cur) { pv.innerHTML = ''; return; }
    let h = '<div style="margin:8px 0 4px"><b>' + esc(cur.name) + '</b>' + (cur.categories.length ? ' <span style="color:#889">(' + esc(cur.categories.join(', ')) + ')</span>' : '') + '</div>';
    h += '<label style="font-size:12px;color:#99a;display:flex;flex-direction:column;gap:3px">Modus (wie am Gerät eingestellt)<select id="ofl_mode">' +
      cur.modes.map((m, i) => '<option value="' + i + '"' + (i === cur.mode ? ' selected' : '') + '>' + esc(m.name) + ' – ' + m.channels + ' Kanäle' + (m.matrix ? ' (Matrix, nicht möglich)' : '') + '</option>').join('') + '</select></label>';
    if (cur.error) h += '<div style="color:#ff6b5a;margin:8px 0">' + esc(cur.error) + '</div>';
    if (cur.notes.length) h += '<ul style="color:#ffb35a;font-size:13px;margin:8px 0;padding-left:18px">' + cur.notes.map(n => '<li>' + esc(n) + '</li>').join('') + '</ul>';
    const t = cur.type;
    if (t) {
      const inv = {};
      Object.entries(t.map).forEach(([p, i]) => { inv[i] = p; });
      const lim = t.safe_limits || {}, df = t.defaults || {}, lc = t.locked_channels || [];
      h += '<div style="overflow-x:auto;max-height:340px;overflow-y:auto"><table><tr><th>Kanal</th><th>Name in der Datei</th><th>Light-Butler</th><th>Std.</th><th>Grenze</th></tr>';
      for (let i = 1; i <= t.channels; i++) {
        const p = inv[i];
        const lock = t.locked || lc.includes(p);
        h += '<tr><td>' + i + '</td><td>' + esc((t.desc || {})[p] || '') + '</td><td>' + (lock ? '<span style="color:#ff6b5a">gesperrt</span>' : esc(role(p) || p)) +
          '</td><td>' + (lock ? 0 : (df[p] || 0)) + '</td><td>' + (lim[p] ? lim[p][0] + '–' + lim[p][1] : '') + '</td></tr>';
      }
      h += '</table></div>';
      h += '<small style="color:#889;display:block;margin:6px 0">Gruppe danach wählbar: ' + esc(cur.groups.map(g => GRP[g] || g).join(', ')) +
        '. Daten aus der Open Fixture Library werden von Hand gepflegt und können Fehler haben: vor dem ersten Einsatz am Gerät prüfen.</small>';
      h += '<div class="ebtn"><button class="ok" id="ofl_save">Als Gerätetyp übernehmen</button></div>';
    }
    pv.innerHTML = h;
    pv.querySelector('#ofl_mode').onchange = e => load(box, Number(e.target.value));
    const sb = pv.querySelector('#ofl_save');
    if (sb) sb.onclick = () => box._save({ fixture: cur.fixture, maker: cur.maker, mode: cur.mode, source: src });
  }

  async function load(box, m) {
    mode = m;
    const st = box.querySelector('#ofl_st');
    st.textContent = 'Wird umgewandelt …';
    try {
      cur = await getJ('/api/ofl/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fixture: cur.fixture, maker: cur.maker, mode: m }) });
      st.textContent = '';
    } catch (e) { st.textContent = e.message; }
    preview(box);
  }

  function fill(box, label) {
    const sel = box.querySelector('#ofl_fx');
    sel.innerHTML = '<option value="">– ' + esc(label || 'Gerät wählen') + ' (' + list.length + ') –</option>' +
      list.map(x => '<option value="' + esc(x.man + '/' + x.key) + '">' + esc(x.name) + (x.categories && x.categories.length ? ' · ' + esc(x.categories.join(', ')) : '') + '</option>').join('');
  }

  async function search(box) {
    const st = box.querySelector('#ofl_st');
    const q = box.querySelector('#ofl_q').value.trim();
    cur = null; preview(box);
    if (!q) { await byMaker(box); return; }
    st.textContent = 'Suche in der Datenbank …';
    try {
      list = await getJ('/api/ofl/search?q=' + encodeURIComponent(q) + (man ? '&m=' + encodeURIComponent(man) : ''));
      st.textContent = list.length ? '' : 'Nichts gefunden. Anderen Begriff versuchen (zum Beispiel nur das Modell, „Spot 60“).';
    } catch (e) { list = []; st.textContent = e.message; }
    fill(box, 'Treffer, Gerät wählen');
  }

  async function byMaker(box) {
    const st = box.querySelector('#ofl_st');
    list = [];
    if (man) {
      st.textContent = 'Geräte werden geladen …';
      try { list = (await getJ('/api/ofl/man?m=' + encodeURIComponent(man))).fixtures.map(x => Object.assign({ man }, x)); st.textContent = ''; } catch (e) { st.textContent = e.message; }
    }
    fill(box, man ? 'Gerät wählen' : 'zuerst suchen oder Hersteller wählen');
  }

  async function open(box, save) {
    box._save = save;
    cur = null; man = ''; list = [];
    box.innerHTML = '<div style="font-size:13px;color:#aab;margin-bottom:6px">Gerätetyp aus der <b>Open Fixture Library</b> (open-fixture-library.org) oder aus einer Datei</div>' +
      '<div class="row"><label class="wide" style="grid-column:1/3">Suche in der ganzen Datenbank (Hersteller, Modell, Art)' +
      '<span style="display:flex;gap:6px"><input id="ofl_q" placeholder="z. B. Vega Spot, Flat PAR, Wash 7x10" style="flex:1"><button id="ofl_go" style="flex:0 0 auto">Suchen</button></span></label>' +
      '<label class="wide" style="grid-column:1/3">Hersteller (wahlweise, schränkt die Suche ein)<select id="ofl_man"><option value="">Wird geladen …</option></select></label>' +
      '<label class="wide" style="grid-column:1/3">Gerät<select id="ofl_fx"><option value="">– zuerst suchen oder Hersteller wählen –</option></select></label></div>' +
      '<div class="ebtn"><label style="flex:1;font-size:12px;color:#99a">Oder Datei importieren (.json von der Gerät-Seite „Download → OFL“, Light-Butler-Export oder QLC+ .qxf)<input type="file" id="ofl_file" accept=".json,.qxf,application/json,text/xml"></label></div>' +
      '<div id="ofl_st" style="color:#ff6b5a;font-size:13px;margin:4px 0"></div><div id="ofl_pv"></div>';
    const st = box.querySelector('#ofl_st');
    const ms = box.querySelector('#ofl_man');
    try {
      const mans = await getJ('/api/ofl/man');
      ms.innerHTML = '<option value="">alle Hersteller (' + mans.length + ')</option>' + mans.map(m => '<option value="' + esc(m.key) + '">' + esc(m.name) + ' (' + m.count + ')</option>').join('');
    } catch (e) { ms.innerHTML = '<option value="">nicht erreichbar</option>'; st.textContent = e.message + ' – Datei-Import geht trotzdem.'; }
    ms.onchange = async () => {
      man = ms.value;
      if (box.querySelector('#ofl_q').value.trim()) await search(box); else { cur = null; preview(box); await byMaker(box); }
    };
    box.querySelector('#ofl_go').onclick = () => search(box);
    box.querySelector('#ofl_q').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); search(box); } };
    box.querySelector('#ofl_fx').onchange = async e => {
      const v = e.target.value;
      if (!v) { cur = null; preview(box); return; }
      const [m, k] = v.split('/');
      st.textContent = 'Gerät wird geladen …';
      try {
        cur = await getJ('/api/ofl/fx?m=' + encodeURIComponent(m) + '&f=' + encodeURIComponent(k));
        src = 'ofl:' + m + '/' + k;
        st.textContent = '';
      } catch (err) { st.textContent = err.message; cur = null; }
      preview(box);
    };
    box.querySelector('#ofl_file').onchange = async e => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 2000000) { st.textContent = 'Die Datei ist zu groß'; return; }
      st.textContent = 'Datei wird gelesen …';
      try {
        cur = await getJ('/api/ofl/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: await f.text() }) });
        src = 'datei:' + f.name.slice(0, 80);
        st.textContent = '';
      } catch (err) { st.textContent = err.message; cur = null; }
      preview(box);
    };
  }

  window.OFL = { open, role };
})();
