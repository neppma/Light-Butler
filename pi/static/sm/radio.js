// radio.js - Seite Internetradio (/musik/radio, 21.11.2026). Sender suchen (radio-browser.info ueber den Licht-Rechner),
// Programmplaetze 1-12, Favoriten, Abspielen. Gespielt wird im Light-Butler Helfer am Musik-Rechner (radio_play.py),
// der den Ton auch an den Licht-Rechner schickt. Diese Seite ist nur die Fernbedienung: man kann sie schliessen.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let S = null, list = [], pickFor = null, volT = null;
  const NET = 'Musik-Rechner (Netzwerk)';

  async function op(name, data) {
    const r = await fetch('/api/sm/cmd', { method: 'POST', body: JSON.stringify(Object.assign({ op: name }, data || {})) });
    const d = await r.json().catch(() => ({ error: 'Antwort nicht lesbar' }));
    if (!r.ok || d.error) throw new Error(d.error || r.statusText);
    return d;
  }
  const logoUrl = st => '/api/sm/radio_logo?u=' + encodeURIComponent(st.uuid);
  function logoImg(st, px) {
    const ini = esc((st.name || '?').replace(/[^A-Za-z0-9ÄÖÜäöü]/g, '').slice(0, 3));
    const sz = 'width:' + px + 'px;height:' + px + 'px;border-radius:6px;background:#10121a;';
    return '<span class="ph" style="position:relative;flex:0 0 auto;' + sz + 'font-size:' + Math.round(px / 3.2) + 'px">' + ini +
      (st.logo ? '<img style="position:absolute;inset:0;' + sz + 'object-fit:contain" loading="lazy" src="' + logoUrl(st) + '" onerror="this.remove()" alt="">' : '') + '</span>';
  }
  const isFav = st => !!(S && S.favs.some(f => f.uuid === st.uuid));
  const meta = st => [st.country, st.tags && st.tags.split(',').slice(0, 3).join(', '), st.codec && (st.codec + (st.kbps ? ' ' + st.kbps + ' kbit/s' : ''))].filter(Boolean).join(' · ');

  function drawNow() {
    const w = S.want, st = w.st, rep = S.rep || {};
    $('nst').textContent = st ? st.name : 'Kein Sender gewählt';
    $('nmeta').textContent = st ? meta(st) : '';
    const lg = $('nlogo');
    if (st && st.logo) { if (lg.dataset.u !== st.uuid) { lg.dataset.u = st.uuid; lg.src = logoUrl(st); } lg.style.visibility = ''; } else lg.style.visibility = 'hidden';
    const song = S.song;
    $('nsong').textContent = song ? song.artist + ' – ' + song.title : (rep.title || '');
    $('ngenre').textContent = song ? (song.genre ? 'Genre ' + song.genre + ' · Licht-Stil danach' : song.done ? 'Genre nicht gefunden' : 'Genre wird gesucht …') : (rep.title ? 'Info vom Sender (kein Lied)' : '');
    const cv = $('ncover');
    if (song && song.cover) { const k = song.artist + '|' + song.title; if (cv.dataset.k !== k) { cv.dataset.k = k; cv.src = '/api/sm/radio_cover?k=' + encodeURIComponent(k); } cv.style.display = ''; }
    else cv.style.display = 'none';
    if (document.activeElement !== $('vol')) { $('vol').value = Math.round(w.vol * 100); $('volv').textContent = Math.round(w.vol * 100) + ' %'; }
    let h = '';
    if (w.play && !S.helper) h += '<div class="err">Der Light-Butler Helfer am Musik-Rechner meldet sich nicht. Er spielt das Radio: Helfer starten (App „Light-Butler Helfer“).</div>';
    else if (w.play && rep.state === 'verbinde') h += '<div class="dim" style="margin-top:6px">Verbinde …</div>';
    else if (w.play && rep.state === 'fehler') h += '<div class="err">' + esc(rep.err || 'Sender nicht erreichbar') + ' (neuer Versuch alle 10 s)</div>';
    if (w.play && !S.sim && !S.net) h += '<div class="warn">Fürs Licht: Am Light-Butler ist der Eingang „' + esc(S.input || '?') + '“ gewählt. <button id="netbtn" class="ib" style="padding:0 8px">Auf ' + NET + ' umschalten</button></div>';
    $('hint').innerHTML = h;
    const nb = $('netbtn');
    if (nb) nb.onclick = async () => {
      await fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ audio: { device: NET } }) }).catch(() => {});
      load();
    };
  }

  function drawSlots() {
    const box = $('slots'), cur = S.want.st && S.want.st.uuid;
    let h = '';
    for (let i = 1; i <= 12; i++) {
      const st = S.slots[i];
      h += st ? '<div class="slot' + (cur === st.uuid && S.want.play ? ' on' : '') + '" data-n="' + i + '"><b>' + i + '</b>' + logoImg(st, 26) +
        '<span>' + esc(st.name) + '</span><i class="x" data-x="' + i + '">✕</i></div>'
        : '<div class="slot empty"><b>' + i + '</b><span>frei</span></div>';
    }
    if (box.dataset.h === h) return;                   // unveraendert: Logos nicht neu laden
    box.dataset.h = h;
    box.innerHTML = h;
    box.querySelectorAll('.slot[data-n]').forEach(el => {
      el.onclick = async e => {
        const x = e.target.dataset.x;
        try { S = Object.assign(S, x ? await op('radio_slot_clear', { n: Number(x) }) : await op('radio_play', { slot: Number(el.dataset.n) })); draw(); } catch (err) { alert(err.message); }
      };
    });
  }

  function drawList() {
    const only = $('onlyfav').checked, rows = only ? S.favs : list;
    $('lst').textContent = only ? S.favs.length + ' Favoriten' : (list.length ? list.length + ' Sender' : '');
    $('list').innerHTML = rows.map((st, i) => '<div class="row" data-i="' + i + '" data-u="' + esc(st.uuid) + '">' + logoImg(st, 40) + '<div class="n"><div>' + esc(st.name) + '</div><div class="dim">' + esc(meta(st)) + '</div></div>' +
      '<button class="ib' + (isFav(st) ? ' fav' : '') + '" data-a="fav" title="Favorit">' + (isFav(st) ? '♥' : '♡') + '</button>' +
      '<button class="ib" data-a="slot" title="Auf einen Programmplatz">+</button><button class="ib" data-a="play" title="Abspielen">▶</button></div>').join('');
    markCur();
    $('list').querySelectorAll('.row').forEach(el => {
      const st = rows[Number(el.dataset.i)];
      el.querySelectorAll('button').forEach(b => {
        b.onclick = async () => {
          try {
            if (b.dataset.a === 'play') S = Object.assign(S, await op('radio_play', { st }));
            else if (b.dataset.a === 'fav') S = Object.assign(S, await op('radio_fav', { st, on: !isFav(st) }));
            else { pickFor = st; drawPick(); return; }
            draw();
          } catch (err) { alert(err.message); }
        };
      });
    });
  }

  function markCur() {
    // Laufender Sender in der Liste: orange umrandet und angehoben (Wunsch 21.11.2026)
    const cur = S && S.want.play && S.want.st ? S.want.st.uuid : '';
    document.querySelectorAll('#list .row').forEach(el => el.classList.toggle('cur', !!cur && el.dataset.u === cur));
  }

  function drawPick() {
    const box = $('pick');
    if (!pickFor) { box.innerHTML = ''; return; }
    let h = '<div class="card" style="margin:6px 0">„' + esc(pickFor.name) + '“ auf Platz:<div class="pick">';
    for (let i = 1; i <= 12; i++) h += '<button data-n="' + i + '">' + i + (S.slots[i] ? '<div class="dim">' + esc(S.slots[i].name.slice(0, 10)) + '</div>' : '') + '</button>';
    box.innerHTML = h + '</div><div style="margin-top:6px"><button id="pickno">Abbrechen</button></div></div>';
    box.querySelectorAll('.pick button').forEach(b => {
      b.onclick = async () => {
        try { S = Object.assign(S, await op('radio_slot_set', { n: Number(b.dataset.n), st: pickFor })); pickFor = null; drawPick(); draw(); } catch (err) { alert(err.message); }
      };
    });
    $('pickno').onclick = () => { pickFor = null; drawPick(); };
    box.scrollIntoView({ block: 'nearest' });
  }

  function draw() { drawNow(); drawSlots(); drawList(); }

  async function load() {
    try { S = await (await fetch('/api/sm/radio', { cache: 'no-store' })).json(); drawNow(); drawSlots(); markCur(); } catch (e) { /* naechster Versuch */ }
  }

  async function search() {
    $('lst').textContent = 'Suche …';
    try {
      list = (await op('radio_search', { cc: $('cc').value, tag: $('tag').value, q: $('q').value.trim() })).stations;
      $('onlyfav').checked = false;
      drawList();
    } catch (e) { $('lst').textContent = e.message; }
  }

  async function init() {
    await load();
    if (S) drawList();
    $('play').onclick = async () => { try { S = Object.assign(S, await op('radio_play', {})); draw(); } catch (e) { alert(e.message); } };
    $('stop').onclick = async () => { try { S = Object.assign(S, await op('radio_stop', {})); draw(); } catch (e) { alert(e.message); } };
    $('vol').oninput = () => {
      $('volv').textContent = $('vol').value + ' %';
      clearTimeout(volT);
      volT = setTimeout(() => op('radio_vol', { v: Number($('vol').value) / 100 }).catch(() => {}), 200);
    };
    $('editbtn').onclick = () => { document.body.classList.toggle('edit'); $('editbtn').textContent = document.body.classList.contains('edit') ? 'Fertig' : 'Bearbeiten'; };
    $('go').onclick = search;
    $('q').onkeydown = e => { if (e.key === 'Enter') search(); };
    $('cc').onchange = search;
    $('tag').onchange = search;
    $('onlyfav').onchange = drawList;
    try {
      const cs = (await op('radio_countries')).countries;
      const want = (S && S.cc) || 'AT';
      $('cc').innerHTML = '<option value="">alle Länder</option>' + cs.map(c => '<option value="' + c.cc + '"' + (c.cc === want ? ' selected' : '') + '>' + esc(c.name) + ' (' + c.n + ')</option>').join('');
      const ts = (await op('radio_tags')).tags;
      $('tag').innerHTML = '<option value="">alle Genres</option>' + ts.map(t => '<option>' + esc(t) + '</option>').join('');
      search();
    } catch (e) { $('cc').innerHTML = '<option value="">Senderliste nicht erreichbar</option>'; $('lst').textContent = e.message; }
    setInterval(load, 2000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
