// radio.js - Seite Internetradio (/musik/radio, 21.11.2026). Sender suchen (radio-browser.info ueber den Licht-Rechner),
// Programmplaetze 1-12, Favoriten, Abspielen. Gespielt wird im Light-Butler Helfer am Musik-Rechner (radio_play.py),
// der den Ton auch an den Licht-Rechner schickt. Diese Seite ist nur die Fernbedienung: man kann sie schliessen.
// Ton: dieses Geraet (22.11.2026): der Browser spielt selbst (<audio>), meldet alle 2 s radio_here, der Helfer schweigt;
// mit Haken Line-In stellt der Licht-Rechner seinen Eingang solange auf Line-In (Fernseher am Line-In) und danach zurueck.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let S = null, list = [], pickFor = null, volT = null;
  const NET = 'Musik-Rechner (Netzwerk)';
  const ls = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ohne Speicher: nur fuer diese Sitzung */ } };
  let DEV = ls('radio_dev', '');
  if (!DEV) { DEV = 'b' + Math.random().toString(36).slice(2, 12); lsSet('radio_dev', DEV); }
  let WHERE = ls('radio_ton', 'mac'), LINE = ls('radio_line', '1') === '1';
  // Fernseher-Ansicht (23.11.2026): je Browser gemerkt; ohne Wahl schaltet sie sich am Fernseher von selbst ein (Kennung des Browsers),
  // ?tv=1 / ?tv=0 in der Adresse setzt sie. In ihr gilt immer Ton: dieses Geraet mit Line-In.
  const TV_UA = /Android.{0,40}TV|GoogleTV|Google TV|BRAVIA|AFT[A-Z]|SMART-?TV|Tizen|Web0S|webOS|HbbTV|CrKey|AndroidTV/i;
  const qtv = new URLSearchParams(location.search).get('tv');
  if (qtv === '1' || qtv === '0') lsSet('radio_tv', qtv);
  let TV = ls('radio_tv', '') ? ls('radio_tv', '') === '1' : TV_UA.test(navigator.userAgent || '');
  const where = () => TV ? 'here' : WHERE;
  const line = () => TV ? true : LINE;
  function applyTv() {
    document.body.classList.toggle('tv', TV);
    if (TV) document.body.classList.remove('edit');
    $('tvbtn').textContent = TV ? '↩ Normale Ansicht' : '📺 Fernseher-Ansicht';
  }
  let auState = 'aus', auErr = '', auBlocked = false, hereT = 0;
  const au = () => $('au');
  const mine = () => !!(S && S.want.play && S.want.here && S.want.dev === DEV);
  const playArgs = x => Object.assign(x || {}, where() === 'here' ? { here: true, dev: DEV } : {});

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
    if (song && song.cover) { const k = song.artist + '|' + song.title; if (cv.dataset.k !== k) { cv.dataset.k = k; cv.src = '/api/sm/radio_cover?k=' + encodeURIComponent(k); } cv.style.visibility = ''; }
    else cv.style.visibility = 'hidden';                 // Platz bleibt: nichts springt
    if (document.activeElement !== $('vol')) { $('vol').value = Math.round(w.vol * 100); $('volv').textContent = Math.round(w.vol * 100) + ' %'; }
    let h = '';
    if (w.play && w.here) {
      if (!mine()) h += '<div class="dim" style="margin-top:6px">Spielt auf einem anderen Gerät (dort im Browser).</div>';
      else if (auBlocked) h += '<div class="warn">Der Browser wartet auf einen Tipp: <button id="aubtn" class="ib" style="padding:0 8px">▶ Ton hier starten</button></div>';
      else if (auState === 'verbinde') h += '<div class="dim" style="margin-top:6px">Verbinde …</div>';
      else if (auState === 'fehler') h += '<div class="err">' + esc(auErr || 'Sender spielt in diesem Browser nicht') + '</div>';
      const li = S.line || {};
      if (mine() && line() && li.auto) h += '<div class="dim" style="margin-top:6px">Eingang am Light-Butler: ' + esc(li.cur) + (li.prev ? ' (danach wieder ' + esc(li.prev) + ')' : '') + '</div>';
      else if (mine() && line() && li.err) h += '<div class="err">' + esc(li.err) + '</div>';
      else if (mine() && !line() && !S.sim && S.net) h += '<div class="warn">Fürs Licht: Am Light-Butler ist der Eingang „' + esc(S.input) + '“ gewählt, der Ton dieses Geräts kommt dort nicht an.</div>';
    } else if (w.play && !S.helper) h += '<div class="err">Der Light-Butler Helfer am Musik-Rechner meldet sich nicht. Er spielt das Radio: Helfer starten (App „Light-Butler Helfer“).</div>';
    else if (w.play && rep.state === 'verbinde') h += '<div class="dim" style="margin-top:6px">Verbinde …</div>';
    else if (w.play && rep.state === 'fehler') h += '<div class="err">' + esc(rep.err || 'Sender nicht erreichbar') + ' (neuer Versuch alle 10 s)</div>';
    if (w.play && !w.here && !S.sim && !S.net) h += '<div class="warn">Fürs Licht: Am Light-Butler ist der Eingang „' + esc(S.input || '?') + '“ gewählt. <button id="netbtn" class="ib" style="padding:0 8px">Auf ' + NET + ' umschalten</button></div>';
    $('hint').innerHTML = h;
    const ab = $('aubtn');
    if (ab) ab.onclick = () => { auBlocked = false; au().play().catch(() => { auBlocked = true; }); drawNow(); };
    document.querySelectorAll('#where button').forEach(b => b.classList.toggle('on', b.dataset.w === WHERE));
    $('herebox').style.display = where() === 'here' ? '' : 'none';
    $('linedev').textContent = S.line_dev ? ' („' + S.line_dev + '“)' : '';
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
      h += st ? '<div class="slot' + (cur === st.uuid && S.want.play ? ' on' : '') + '" tabindex="0" role="button" data-n="' + i + '"><b>' + i + '</b>' + logoImg(st, 26) +
        '<span>' + esc(st.name) + '</span><i class="x" data-x="' + i + '">✕</i></div>'
        : '<div class="slot empty"><b>' + i + '</b><span>frei</span></div>';
    }
    if (box.dataset.h === h) return;                   // unveraendert: Logos nicht neu laden
    box.dataset.h = h;
    box.innerHTML = h;
    box.querySelectorAll('.slot[data-n]').forEach(el => {
      el.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.click(); } };   // Fernbedienung: OK
      el.onclick = async e => {
        const x = e.target.dataset.x;
        try { S = Object.assign(S, x ? await op('radio_slot_clear', { n: Number(x) }) : await op('radio_play', playArgs({ slot: Number(el.dataset.n) }))); draw(); } catch (err) { alert(err.message); }
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
            if (b.dataset.a === 'play') S = Object.assign(S, await op('radio_play', playArgs({ st })));
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

  function draw() { sync(); drawNow(); drawSlots(); drawList(); }

  // ---- Ton in diesem Browser -------------------------------------------------------------------
  function sync() {
    const a = au();
    if (mine()) {
      const url = S.want.st.url;
      if (a.dataset.u !== url) {
        a.dataset.u = url;
        auState = 'verbinde'; auErr = '';
        if (S.want.st.hls && !a.canPlayType('application/vnd.apple.mpegurl')) { auState = 'fehler'; auErr = 'Dieser Sender sendet HLS, das spielt dieser Browser nicht. Bitte einen anderen Sender wählen.'; }
        else { a.src = url; a.play().then(() => { auBlocked = false; }).catch(() => { auBlocked = true; }); }
        report();
      }
      a.volume = Math.max(0, Math.min(1, S.want.vol));
    } else if (a.dataset.u) {
      a.pause(); a.removeAttribute('src'); a.load(); delete a.dataset.u;
      auState = 'aus'; auBlocked = false;
    }
  }

  async function report() {
    if (!mine()) return;
    hereT = Date.now();
    try {
      const r = await op('radio_here', { dev: DEV, state: auBlocked ? 'verbinde' : auState, err: auErr, line: line() });
      if (r.other) { S.want.here = false; sync(); }
      if (r.line) S.line = r.line;
    } catch (e) { /* naechster Versuch */ }
  }

  async function load() {
    try { S = await (await fetch('/api/sm/radio', { cache: 'no-store' })).json(); sync(); drawNow(); drawSlots(); markCur(); } catch (e) { /* naechster Versuch */ }
    if (mine() && Date.now() - hereT >= 1900) report();
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
    $('play').onclick = async () => { try { S = Object.assign(S, await op('radio_play', playArgs())); draw(); } catch (e) { alert(e.message); } };
    $('stop').onclick = async () => { try { S = Object.assign(S, await op('radio_stop', {})); draw(); } catch (e) { alert(e.message); } };
    $('vol').oninput = () => {
      $('volv').textContent = $('vol').value + ' %';
      clearTimeout(volT);
      volT = setTimeout(() => op('radio_vol', { v: Number($('vol').value) / 100 }).catch(() => {}), 200);
    };
    document.querySelectorAll('#where button').forEach(b => {
      b.onclick = async () => {
        if (WHERE === b.dataset.w) return;
        WHERE = b.dataset.w; lsSet('radio_ton', WHERE);
        if (S && S.want.play && S.want.st) { try { S = Object.assign(S, await op('radio_play', playArgs({ st: S.want.st }))); } catch (e) { alert(e.message); } }
        draw();
      };
    });
    $('line').checked = LINE;
    $('line').onchange = () => { LINE = $('line').checked; lsSet('radio_line', LINE ? '1' : '0'); report(); };
    const a = au();
    a.addEventListener('playing', () => { auState = 'spielt'; auErr = ''; auBlocked = false; report(); drawNow(); });
    a.addEventListener('waiting', () => { if (auState !== 'fehler') { auState = 'verbinde'; drawNow(); } });
    a.addEventListener('error', () => { if (!a.dataset.u) return; auState = 'fehler'; auErr = 'Sender spielt in diesem Browser nicht (Format oder Verbindung)'; report(); drawNow(); });
    a.addEventListener('pause', () => { if (mine() && !auBlocked) { auState = 'aus'; report(); } });
    window.addEventListener('pagehide', () => {
      if (!mine()) return;
      try { navigator.sendBeacon('/api/sm/cmd', JSON.stringify({ op: 'radio_here', dev: DEV, state: 'aus', line: line() })); } catch (e) { /* egal */ }
    });
    applyTv();
    $('tvbtn').onclick = async () => {
      TV = !TV; lsSet('radio_tv', TV ? '1' : '0'); applyTv();
      if (S && S.want.play && S.want.st && mine() !== (where() === 'here')) { try { S = Object.assign(S, await op('radio_play', playArgs({ st: S.want.st }))); } catch (e) { alert(e.message); } }
      draw();
      if (TV) { const f = document.querySelector('.slot.on') || document.querySelector('.slot[data-n]'); if (f) f.focus(); }
    };
    if (TV) setTimeout(() => { const f = document.querySelector('.slot.on') || document.querySelector('.slot[data-n]'); if (f) f.focus(); }, 300);
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
