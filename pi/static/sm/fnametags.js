// Tags aus dem Dateinamen (Wunsch 10.11.2026). Der Mac liest Ordner und Tags (GET /fnametags) und schreibt nur auf Knopfdruck
// (POST /fnametags, mac/mixxx_bridge/fname_tags.py). Vorhoeren mit der Leiste unten, Tag-Fenster je Lied, Seiten zu 20 Liedern.
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const mmss = s => s ? Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0') : '';
  const audio = new Audio();
  const PAGE = 20, LBL = { artist: 'Interpret', title: 'Titel', track: 'Track' };
  let music = '', data = null, playing = '', off = new Set(), busy = false, page = 0, stamp = Date.now();
  const pbar = SM.playBar(audio, { onclose: () => { playing = ''; draw(); } });

  async function mac(path, body) {
    if (!music) music = ((await fetch('/api/musik/mac').then(r => r.json())) || {}).music || '';
    if (!music) throw new Error('Der Light-Butler erreicht den Musik-Rechner gerade nicht. Läuft dort der Light-Butler Helfer oder die Mixxx-App?');
    const r = await fetch(music + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
    let d = null;
    try { d = JSON.parse(await r.text()); } catch (e) { d = null; }
    if (r.status === 404 || !d) throw new Error('Am Musik-Rechner läuft noch die alte Fassung: Helfer oder Mixxx-App neu installieren (./deploy.sh alles).');
    if (!r.ok) throw new Error(d.error || 'ging nicht (' + r.status + ')');
    return d;
  }
  async function init() {
    try {
      const d = await mac('/fnametags');
      $('dirs').innerHTML = (d.dirs || []).map(([p, n]) => '<option value="' + esc(p) + '">' + n + ' Lieder</option>').join('');
      $('pat').innerHTML = (d.patterns || []).map(([k, l]) => '<option value="' + k + '">' + esc(l) + '</option>').join('');
      const q = new URLSearchParams(location.search);
      if (q.get('dir')) { $('dir').value = q.get('dir'); if (q.get('pat')) $('pat').value = q.get('pat'); load(); }
    } catch (e) { $('msg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; }
  }
  async function load() {
    const d = $('dir').value.trim();
    if (!d) { $('msg').textContent = 'Ordner wählen.'; return; }
    $('msg').textContent = 'Lese die Tags in ' + d + ' …';
    try {
      data = await mac('/fnametags?dir=' + encodeURIComponent(d) + '&pat=' + encodeURIComponent($('pat').value) + '&ow=' + ($('ow').checked ? 1 : 0));
      stamp = Date.now(); off = new Set();
      $('msg').textContent = data.n + ' Lieder in ' + data.dir + ', bei ' + data.todo + ' kommt etwas ins Tag.';
    } catch (e) { data = null; $('msg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; }
    draw();
  }

  const songs = () => (data && data.songs) || [];
  const pages = () => Math.max(1, Math.ceil(songs().length / PAGE));
  function shown() { page = Math.max(0, Math.min(page, pages() - 1)); return songs().slice(page * PAGE, page * PAGE + PAGE).map((s, k) => ({ s, si: page * PAGE + k })); }
  function pager() {
    const n = songs().length, pg = pages();
    if (pg <= 1) return '';
    return '<div class="pager"><button class="pgprev"' + (page ? '' : ' disabled') + '>‹ Zurück</button><span>Seite <b>' + (page + 1) + '</b> von ' + pg +
      ' · Lieder ' + (page * PAGE + 1) + '–' + Math.min(n, page * PAGE + PAGE) + ' von ' + n + '</span><button class="pgnext"' + (page < pg - 1 ? '' : ' disabled') + '>Weiter ›</button></div>';
  }
  const fieldTxt = (o, ch) => ['artist', 'title', 'track'].filter(k => o[k]).map(k => (ch && ch[k] ? '<span class="new">' : '<span class="same">') + LBL[k] + ': ' + esc(o[k]) + '</span>').join('<br>') || '<span class="dim">–</span>';

  function draw() {
    const list = shown();
    if (!list.length) { $('list').innerHTML = ''; summary(); return; }
    const rows = list.map(({ s, si }) => {
      const has = Object.keys(s.change).length, on = has && !off.has(s.path);
      return '<tr class="' + (on ? '' : 'off') + '"><td>' + (has ? '<input type="checkbox" data-c="' + si + '"' + (on ? ' checked' : '') + '>' : '') + '</td>' +
        '<td><div class="cell1"><img class="cvimg" loading="lazy" alt="" src="' + music + '/cover?p=' + encodeURIComponent(s.path) + '&v=' + stamp + '" onerror="this.style.visibility=&quot;hidden&quot;"><span>' +
        '<button class="pb' + (playing === s.path ? ' on' : '') + '" data-p="' + si + '" title="Vorhören">' + (playing === s.path && !audio.paused ? '❚❚' : '▶') + '</button>' +
        '<button class="pb" data-t="' + si + '" title="Tag bearbeiten">Tag</button></span></div></td>' +
        '<td>' + esc(s.rel.split('/').pop()) + '<div class="dim" style="font-size:11.5px">' + esc(s.rel.split('/').slice(0, -1).join('/')) + '</div></td>' +
        '<td class="num">' + mmss(s.dur) + '</td><td>' + fieldTxt(s.cur, null) + '</td><td>' + (has ? fieldTxt(Object.assign({}, s.cur, s.change), s.change) : '<span class="dim">nichts zu tun</span>') + '</td></tr>';
    }).join('');
    $('list').innerHTML = pager() + '<div class="fold"><table><colgroup><col class="c-on"><col class="c-pl"><col class="c-file"><col class="c-len"><col><col></colgroup>' +
      '<thead><tr><th></th><th></th><th>Datei</th><th>Länge</th><th>Jetzt im Tag</th><th>Danach</th></tr></thead><tbody>' + rows + '</tbody></table></div>' + pager();
    summary();
  }
  function items() { return shown().filter(({ s }) => Object.keys(s.change).length && !off.has(s.path)).map(({ s }) => ({ path: s.path, file: s.file, fields: s.change })); }
  function summary() {
    const it = items();
    $('gosum').textContent = shown().length ? 'Diese Seite: ' + (it.length ? it.length + ' Lieder bekommen Angaben aus dem Dateinamen.' : 'nichts einzutragen.') : '';
    $('bgo').disabled = busy || !it.length;
  }
  function play(s) {
    if (playing === s.path && !audio.paused) { audio.pause(); draw(); return; }
    if (playing !== s.path) { playing = s.path; audio.src = music + '/audio?p=' + encodeURIComponent(s.path); }
    audio.play().catch(e => SM.toast('Abspielen ging nicht: ' + e.message, 4000));
    pbar.show(s.rel.split('/').pop());
    draw();
  }
  audio.addEventListener('pause', () => draw());
  audio.addEventListener('play', () => draw());
  $('list').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.classList.contains('pgprev') || b.classList.contains('pgnext')) { page += b.classList.contains('pgnext') ? 1 : -1; draw(); window.scrollTo(0, 0); return; }
    const s = songs()[+(b.dataset.p || b.dataset.t)]; if (!s) return;
    if (b.dataset.p) play(s);
    else if (b.dataset.t) SM.tagEdit({ path: s.path, dur: s.dur || 0 }, music, () => { setTimeout(load, 400); });
  });
  $('list').addEventListener('change', e => {
    const el = e.target; if (!el.dataset.c) return;
    const s = songs()[+el.dataset.c];
    if (el.checked) off.delete(s.path); else off.add(s.path);
    draw();
  });
  $('bload').onclick = () => { page = 0; load(); };
  $('pat').onchange = () => { if (data) load(); };
  $('ow').onchange = () => { if (data) load(); };
  $('dir').addEventListener('keydown', e => { if (e.key === 'Enter') { page = 0; load(); } });
  $('bgo').onclick = async () => {
    const it = items(); if (!it.length) return;
    if (!await SM.ask(it.length + ' Lieder bekommen Angaben aus dem Dateinamen ins Tag. Jetzt eintragen?', undefined, 'Eintragen')) return;
    busy = true; summary();
    try {
      const r = await mac('/fnametags', { op: 'apply', items: it });
      const msg = '<span class="ok">' + r.written + ' Lieder eingetragen.</span>' + (r.errors && r.errors.length ? ' <span class="bad">' + r.errors.length + ' gingen nicht: ' + esc(r.errors.slice(0, 3).join('; ')) + '</span>' : '');
      await load();
      $('msg').innerHTML = msg;
    } catch (e) { $('msg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; }
    busy = false; summary();
  };
  init();
})();
