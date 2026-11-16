// Gruppen-Manager (Wunsch von Markus, 13.11.2026): alle Gruppen (Feld Gruppe/TIT1 im Tag) mit Zahl der Lieder; Lieder einer Gruppe
// anhaken und verschieben, zusaetzlich zuordnen oder herausnehmen; ganze Gruppe umbenennen, zusammenlegen, aufloesen.
// Liste vom Pi (/api/musik, Feld grp); geschrieben wird am Musik-Rechner (music_serve /genres op group -> genre_edit.set_grouping,
// Protokoll und Zuruecknehmen wie im Genre-Editor).
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const NONE = '\u0000ohne', PER = 100;
  let tracks = [], music = '', cur = '', page = 0, sel = new Set(), busy = false, curSongs = [];
  const audio = new Audio();
  let playing = '';
  const bar = SM.playBar(audio, { onclose: () => { audio.pause(); playing = ''; drawPlay(); } });

  const toks = r => String(r.grp || '').split(';').map(x => x.trim()).filter(Boolean);
  const join = a => [...new Set(a.map(x => x.trim()).filter(Boolean))].join('; ');
  const isMp3 = r => /\.mp3$/i.test(r.path || '');
  const label = g => g === NONE ? 'ohne Gruppe' : g;
  const inGroup = (r, g) => g === NONE ? !toks(r).length : toks(r).includes(g);

  async function load() {
    try {
      const d = await (await fetch('/api/musik')).json();
      tracks = (d.tracks || []).filter(r => r.path);
      music = d.music || music;
    } catch (e) { $('glist').textContent = 'Konnte die Liedliste nicht laden: ' + e.message; return; }
    drawGroups();
    if (cur) drawSongs();
    const g = new URLSearchParams(location.search).get('g');
    if (g && !cur) open(g);
  }

  function counts() {
    const c = {};
    let none = 0;
    for (const r of tracks) { const t = toks(r); if (!t.length) none++; for (const g of t) c[g] = (c[g] || 0) + 1; }
    return { c, none };
  }

  function drawGroups() {
    const { c, none } = counts(), q = $('gq').value.trim().toLowerCase();
    const names = Object.keys(c).filter(g => !q || g.toLowerCase().includes(q)).sort((a, b) => c[b] - c[a] || a.localeCompare(b, 'de'));
    const max = Math.max(1, ...Object.values(c));
    $('ghead').textContent = 'Gruppen (' + Object.keys(c).length + ')';
    $('glist').className = '';
    $('glist').innerHTML = names.map(g => '<div class="g' + (g === cur ? ' cur' : '') + '" data-g="' + esc(g) + '"><span>' + esc(g) + '</span><span class="n">' + c[g] + '</span>' +
      '<div class="bar" style="width:' + Math.max(2, Math.round(100 * c[g] / max)) + '%"></div></div>').join('') +
      '<div class="g none' + (cur === NONE ? ' cur' : '') + '" data-g="' + esc(NONE) + '"><span><i>ohne Gruppe</i></span><span class="n">' + none + '</span></div>' ||
      '<div class="dim">Keine Gruppen.</div>';
    $('tgtl').innerHTML = Object.keys(c).sort((a, b) => a.localeCompare(b, 'de')).map(g => '<option value="' + esc(g) + '">').join('');
  }

  function open(g) {
    cur = g; page = 0; sel = new Set(); $('sq').value = '';
    history.replaceState(null, '', '?g=' + encodeURIComponent(g === NONE ? '' : g));
    drawGroups(); drawSongs();
  }

  function drawSongs() {
    const q = $('sq').value.trim().toLowerCase();
    const all = tracks.filter(r => inGroup(r, cur));
    curSongs = all.filter(r => !q || [r.name, r.artist, r.path, r.album].join(' ').toLowerCase().includes(q))
      .sort((a, b) => String(a.artist || '').localeCompare(String(b.artist || ''), 'de') || String(a.name || '').localeCompare(String(b.name || ''), 'de'));
    const mp3 = all.filter(isMp3).length;
    $('head').className = '';
    $('head').innerHTML = '<h2>' + esc(label(cur)) + '</h2><div class="meta">' + all.length + ' Lied' + (all.length === 1 ? '' : 'er') + (mp3 < all.length ? ', davon ' + mp3 + ' MP3 (nur die lassen sich schreiben)' : '') + '</div>';
    $('gacts').hidden = cur === NONE;
    $('sbar').hidden = false;
    page = Math.max(0, Math.min(page, Math.ceil(curSongs.length / PER) - 1));
    const part = curSongs.slice(page * PER, (page + 1) * PER);
    $('songs').innerHTML = part.map((r, i) => '<div class="song"><input type="checkbox" data-p="' + esc(r.path) + '"' + (sel.has(r.path) ? ' checked' : '') + (isMp3(r) ? '' : ' disabled title="keine MP3"') + '>' +
      '<button class="pb" data-play="' + esc(r.path) + '" data-name="' + esc((r.artist || '') + ' - ' + (r.name || '')) + '">▶</button>' +
      '<img class="cvimg" data-tag="' + (page * PER + i) + '" loading="lazy" alt="" title="Antippen: Tag bearbeiten" src="/api/sm/cover?p=' + encodeURIComponent(r.path) + '" onerror="this.style.visibility=&quot;hidden&quot;">' +
      '<div><div>' + SM.favHtml('song', r.path, { cls: 'sm' }) + esc(r.name || r.title || '') + ' <span class="dim">– ' + esc(r.artist || '') + '</span></div><div class="s">' +
      toks(r).map(g => '<span class="chip' + (g === cur ? ' cur' : '') + '">' + esc(g) + '</span>').join('') + (r.album ? ' ' + esc(r.album) : '') + '</div></div></div>').join('') ||
      '<div class="dim">Keine Lieder.</div>';
    const n = Math.ceil(curSongs.length / PER);
    $('pager').innerHTML = n > 1 ? '<button data-pg="' + (page - 1) + '"' + (page ? '' : ' disabled') + '>‹ zurück</button> Seite ' + (page + 1) + ' von ' + n + ' <button data-pg="' + (page + 1) + '"' + (page < n - 1 ? '' : ' disabled') + '>weiter ›</button>' : '';
    drawSel(); drawPlay();
  }

  function drawSel() {
    $('selbar').hidden = !sel.size;
    $('selc').textContent = sel.size + ' angehakt';
    $('bmove').textContent = cur === NONE ? 'In Gruppe aufnehmen' : 'Verschieben';
    $('badd').hidden = $('bout').hidden = cur === NONE;
  }

  // ---- schreiben (Musik-Rechner) ----
  async function write(pairs, what) {
    if (busy) return;
    pairs = pairs.filter(([p, g]) => { const r = tracks.find(t => t.path === p); return r && isMp3(r) && join(toks(r)) !== g; });
    if (!pairs.length) { SM.toast('Nichts zu ändern.', 3000); return; }
    if (!music) { try { music = ((await (await fetch('/api/musik/mac')).json()) || {}).music || ''; } catch (e) { music = ''; } }
    if (!music) { SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer?).', 5000); return; }
    busy = true;
    $('msg').textContent = what + ': schreibe ' + pairs.length + ' MP3' + (pairs.length === 1 ? '' : 's') + ' …';
    try {
      const r = await fetch(music + '/genres', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'group', pairs, label: what }) });
      const d = await r.json(); if (!r.ok || d.error) throw new Error(d.error || r.statusText);
    } catch (e) { busy = false; $('msg').textContent = 'Gruppe schreiben: ' + e.message; return; }
    let st = null;
    for (let i = 0; i < 900; i++) {
      await new Promise(r => setTimeout(r, 800));
      try { st = await (await fetch(music + '/genres?job=1&field=grouping')).json(); } catch (e) { continue; }
      const j = st.job || {};
      $('msg').textContent = what + ': ' + (j.done || 0) + ' von ' + (j.total || pairs.length) + ' …';
      if (j.state === 'done') break;
    }
    busy = false;
    const j = (st && st.job) || {}, op = ((st && st.ops) || [])[0];
    for (const [p, g] of pairs) { const r = tracks.find(t => t.path === p); if (r) r.grp = g; }   // gleich zeigen, die Liste vom Pi folgt
    sel = new Set();
    $('msg').innerHTML = '<span class="ok">' + esc(what) + ': ' + (j.ok || 0) + ' MP3' + (j.ok === 1 ? '' : 's') + ' geschrieben</span>' +
      (j.skip ? ', ' + j.skip + ' übersprungen' + (j.err ? ' (' + esc(j.err) + ')' : '') : '') + '. ' +
      (op && !op.undone ? '<button class="lnk" data-undo="' + esc(op.id) + '">Zurücknehmen</button>' : '') + ' <span class="dim">Mixxx zeigt es nach „Metadaten aus Datei importieren“.</span>';
    drawGroups(); drawSongs();
    for (const ms of [8000, 30000, 70000]) setTimeout(load, ms);
  }

  function targetName() {
    const t = $('tgt').value.replace(/;/g, ',').replace(/\s+/g, ' ').trim().slice(0, 60);
    if (!t) { SM.toast('Erst eine Ziel-Gruppe wählen oder eintippen.', 4000); $('tgt').focus(); }
    return t;
  }
  const chosen = () => tracks.filter(r => sel.has(r.path));

  $('bmove').onclick = () => {
    const t = targetName(); if (!t) return;
    write(chosen().map(r => [r.path, join(toks(r).filter(g => g !== cur).concat([t]))]), (cur === NONE ? 'In „' : '„' + cur + '“ → „') + t + '“' + (cur === NONE ? ' aufgenommen' : ''));
  };
  $('badd').onclick = () => { const t = targetName(); if (t) write(chosen().map(r => [r.path, join(toks(r).concat([t]))]), 'zusätzlich „' + t + '“'); };
  $('bout').onclick = () => write(chosen().map(r => [r.path, join(toks(r).filter(g => g !== cur))]), 'aus „' + cur + '“ genommen');
  $('bren').onclick = async () => {
    const t0 = await SM.ask('Neuer Name für die Gruppe „' + cur + '“ (alle ' + tracks.filter(r => inGroup(r, cur)).length + ' Lieder). Gibt es den Namen schon, werden beide zusammengelegt.', cur, 'Umbenennen');
    const t = (t0 || '').replace(/;/g, ',').replace(/\s+/g, ' ').trim().slice(0, 60);
    if (!t || t === cur) return;
    const old = cur;
    await write(tracks.filter(r => inGroup(r, old)).map(r => [r.path, join(toks(r).map(g => g === old ? t : g))]), '„' + old + '“ → „' + t + '“');
    open(t);
  };
  $('bdis').onclick = async () => {
    const n = tracks.filter(r => inGroup(r, cur)).length;
    if (!await SM.ask('Gruppe „' + cur + '“ auflösen? Sie kommt aus allen ' + n + ' Liedern heraus, andere Gruppen der Lieder bleiben. Zurücknehmen geht danach.', undefined, 'Auflösen')) return;
    const old = cur;
    await write(tracks.filter(r => inGroup(r, old)).map(r => [r.path, join(toks(r).filter(g => g !== old))]), 'Gruppe „' + old + '“ aufgelöst');
    open(NONE);
  };
  $('msg').addEventListener('click', async e => {
    const b = e.target.closest('[data-undo]'); if (!b) return;
    try {
      const r = await fetch(music + '/genres', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'undo', id: b.dataset.undo }) });
      const d = await r.json(); if (!r.ok || d.error) throw new Error(d.error || r.statusText);
      $('msg').textContent = 'Wird zurückgenommen … die alten Gruppen kommen wieder in die Dateien. Die Liste folgt in einer Minute.';
      for (const ms of [8000, 30000, 70000]) setTimeout(load, ms);
    } catch (x) { SM.toast('Zurücknehmen: ' + x.message, 6000); }
  });

  // ---- Vorhoeren, Tag ----
  function drawPlay() {
    document.querySelectorAll('#songs button[data-play]').forEach(b => { const on = b.dataset.play === playing && !audio.paused; b.classList.toggle('on', on); b.textContent = on ? '❚❚' : '▶'; });
  }
  async function needMusic() {
    if (!music) { try { music = ((await (await fetch('/api/musik/mac')).json()) || {}).music || ''; } catch (e) { music = ''; } }
    if (!music) SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer?).', 5000);
    return !!music;
  }
  audio.addEventListener('pause', drawPlay);
  audio.addEventListener('play', drawPlay);

  // ---- Bedienung ----
  $('glist').addEventListener('click', e => { const g = e.target.closest('.g'); if (g) open(g.dataset.g); });
  $('gq').addEventListener('input', drawGroups);
  $('sq').addEventListener('input', () => { page = 0; drawSongs(); });
  $('songs').addEventListener('change', e => { const c = e.target.closest('input[data-p]'); if (!c) return; if (c.checked) sel.add(c.dataset.p); else sel.delete(c.dataset.p); drawSel(); });
  $('songs').addEventListener('click', async e => {
    const im = e.target.closest('img[data-tag]');
    if (im) { const r = curSongs[+im.dataset.tag]; if (r && await needMusic()) SM.tagEdit({ path: r.path, dur: r.dur || 0 }, music, () => setTimeout(load, 1500)); return; }
    const b = e.target.closest('button[data-play]');
    if (!b || !await needMusic()) return;
    if (playing === b.dataset.play && !audio.paused) { audio.pause(); return; }
    if (playing !== b.dataset.play) { audio.src = music + '/audio?p=' + encodeURIComponent(b.dataset.play); playing = b.dataset.play; }
    try { await audio.play(); bar.show(b.dataset.name); } catch (x) { SM.toast('Abspielen: ' + x.message, 5000); }
  });
  $('sall').onclick = () => { for (const r of curSongs) if (isMp3(r)) sel.add(r.path); drawSongs(); };
  $('snone').onclick = () => { sel = new Set(); drawSongs(); };
  $('pager').addEventListener('click', e => { const b = e.target.closest('button[data-pg]'); if (b && !b.disabled) { page = +b.dataset.pg; drawSongs(); $('right').scrollIntoView({ block: 'start' }); } });
  SM.favLoad();                                          // Herzen (Favoriten, 14.11.2026)
  load();
})();
