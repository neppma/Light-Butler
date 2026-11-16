// Alben (Wunsch von Markus, 13.11.2026): gebaut wie die Interpreten (artists.js). Kacheln mit dem Cover des ersten Liedes, Klick zeigt
// das Album mit seinen Liedern in CD-Reihenfolge und (von Deezer) Datum, Label und Titelliste: was dir fehlt.
// Daten vom Pi (showman/albums.py): /api/sm/albums, /api/sm/album?k= oder ?p=, Befehl album_info.
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const PER = 60;
  let all = [], view = [], page = 0, cur = '', letter = '', music = '', curSongs = [];
  const audio = new Audio();
  let playing = '';
  const bar = SM.playBar(audio, { onclose: () => { audio.pause(); playing = ''; drawSongsBtns(); } });
  let single = false, favOnly = false, areaSel = [], smp = '';
  try {
    single = localStorage.getItem('alb_single') === '1';
    const v = JSON.parse(localStorage.getItem('alb_areas') || 'null');
    areaSel = Array.isArray(v) ? v.filter(x => typeof x === 'string') : [];
    smp = localStorage.getItem('alb_smp') || '';
  } catch (e) { /* privates Fenster */ }
  const store = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* egal */ } };

  const coverUrl = a => '/api/sm/cover?p=' + encodeURIComponent(a.cover || '');
  const face = (a, cls, extra) => '<div class="' + cls + '"><img loading="lazy" alt=""' + (cls === 'big' ? ' class="cvimg" data-zoom="300"' : ' class="cv"') + ' src="' + coverUrl(a) +
    '" onerror="this.style.visibility=&quot;hidden&quot;">' + (extra || '') + '</div>';
  const letterOf = a => { const c = SM.artistKey(a.name)[0] || '#'; return /[a-z]/.test(c) ? c.toUpperCase() : '#'; };
  const dateTxt = s => s ? new Date(s * 1000).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '';
  const who = a => a.sampler ? 'Verschiedene' : (a.artist || '');

  async function load() {
    try {
      SM.favLoad();                                    // Herzen (Favoriten, 14.11.2026)
      const d = await (await fetch('/api/sm/albums')).json();
      all = d.albums || [];
      music = d.music || music;
    } catch (e) { $('astat').textContent = 'Konnte die Alben nicht laden: ' + e.message; return; }
    areas();
    filter(true);
    const m = /k=([^&]+)/.exec(location.hash) || /[?&]k=([^&]+)/.exec(location.search);
    const p = new URLSearchParams(location.search).get('p');
    if (!cur && m) open(decodeURIComponent(m[1]));
    else if (!cur && p) {                                  // aus der Musik-Datenbank: das Album zu diesem Lied
      try { const d = await (await fetch('/api/sm/album?p=' + encodeURIComponent(p))).json(); if (d.k) open(d.k); } catch (e) { /* egal */ }
    }
  }

  // Bereich wie bei den Interpreten: Ordner ("d:KLASSIK") und Gruppen im Tag ("g:Après-Ski"), mehrere, gemerkt
  const inArea = a => !areaSel.length ? a.n : Math.min(a.n, areaSel.reduce((s, v) => s + (((v[0] === 'd' ? a.dirs : a.grps) || {})[v.slice(2)] || 0), 0));
  // Genre (Wunsch 13.11.2026): Lieder des Eintrags in den gewaehlten Genres; zusammen mit dem Bereich zaehlt das Kleinere
  const genP = SM.checkPicker($('genb'), { name: 'Genre', key: 'alb_genres', onChange: () => filter() });
  const inGenre = a => !genP.sel.length ? a.n : Math.min(a.n, genP.sel.reduce((s, g) => s + ((a.gens || {})[g] || 0), 0));
  const cnt = a => Math.min(inArea(a), inGenre(a));
  const area = () => areaSel.length > 0 || genP.sel.length > 0;
  function areas() {
    const D = {}, G = {};
    for (const a of all) { for (const d in a.dirs || {}) D[d] = (D[d] || 0) + 1; for (const g in a.grps || {}) G[g] = (G[g] || 0) + 1; }
    const known = new Set([...Object.keys(D).map(d => 'd:' + d), ...Object.keys(G).map(g => 'g:' + g)]);
    if (all.length) areaSel = areaSel.filter(v => known.has(v));
    const opt = (v, t, n) => '<label><input type="checkbox" value="' + esc(v) + '"' + (areaSel.includes(v) ? ' checked' : '') + '> ' + esc(t) + '<span class="n">' + n + '</span></label>';
    const abc = o => Object.keys(o).sort((x, y) => x.localeCompare(y, 'de'));
    const h = (Object.keys(D).length ? '<div class="ag">Ordner (Zahl der Alben)</div>' + abc(D).map(d => opt('d:' + d, d, D[d])).join('') : '') +
      (Object.keys(G).length ? '<div class="ag">Gruppe im Tag</div>' + abc(G).map(g => opt('g:' + g, g, G[g])).join('') : '') || '<div class="dim">Keine Bereiche bekannt.</div>';
    if ($('areal').dataset.h !== h) { $('areal').innerHTML = h; $('areal').dataset.h = h; }
    const GE = {};
    for (const a of all) for (const g in a.gens || {}) GE[g] = (GE[g] || 0) + 1;
    genP.render([{ title: 'Genre (Zahl der Alben)', items: Object.keys(GE).sort((x, y) => x.localeCompare(y, 'de', { sensitivity: 'base' })).map(g => ({ v: g, t: g, n: GE[g] })) }]);
    areaLabel();
  }
  function areaLabel() {
    const n = areaSel.length, nm = v => v.slice(2);
    $('areab').textContent = 'Bereich: ' + (!n ? 'alle' : n <= 2 ? areaSel.map(nm).join(', ') : nm(areaSel[0]) + ' + ' + (n - 1) + ' weitere') + ' ▾';
    $('areab').classList.toggle('on', n > 0);
  }

  function filter(keep) {
    const q = SM.artistKey($('q').value).replace(/-/g, ' ').trim(), srt = $('sort').value;
    const words = a => (SM.artistKey(a.name) + ' ' + SM.artistKey(who(a))).replace(/-/g, ' ');
    view = all.filter(a => cnt(a) > 0 && (single || favOnly || cnt(a) > 1 || area() || a.k === cur) && (!favOnly || SM.favOf('album', a.k)) && (smp === '' || String(a.sampler) === smp) &&
      (!letter || letterOf(a) === letter) && (!q || words(a).includes(q)));
    const by = { fav: (a, b) => SM.favOf('album', b.k) - SM.favOf('album', a.k) || cnt(b) - cnt(a), n: (a, b) => cnt(b) - cnt(a), plays: (a, b) => b.plays - a.plays || b.n - a.n, last: (a, b) => b.last - a.last || b.n - a.n,
      year: (a, b) => (b.year || 0) - (a.year || 0), yearup: (a, b) => (a.year || 9999) - (b.year || 9999),
      art: (a, b) => SM.artistKey(who(a)).localeCompare(SM.artistKey(who(b))) || (a.year || 0) - (b.year || 0) };
    view.sort((a, b) => (by[srt] ? by[srt](a, b) : 0) || SM.artistKey(a.name).localeCompare(SM.artistKey(b.name)));
    const singles = all.filter(a => a.n === 1).length, samplers = all.filter(a => a.sampler).length;
    $('astat').innerHTML = '<b>' + all.length + '</b> Alben · ' + samplers + ' Sampler' +
      (single || area() ? '' : ' · ' + singles + ' mit nur einem Lied ausgeblendet') + (view.length !== all.length ? ' · gezeigt: ' + view.length : '');
    if (!keep) page = 0;
    page = Math.max(0, Math.min(page, Math.ceil(view.length / PER) - 1));
    draw();
  }

  function pager() {                                       // wie bei den Interpreten: feste Felder, zurueck und weiter vorne
    const n = Math.ceil(view.length / PER);
    if (n <= 1) return '';
    const btn = (p, t, on, cls) => '<button data-pg="' + p + '" class="' + (cls || '') + (on ? ' on' : '') + '"' + (p < 0 || p >= n ? ' disabled' : '') + '>' + t + '</button>';
    const W = 7, nums = [];
    if (n <= W) for (let i = 0; i < n; i++) nums.push(i);
    else if (page < 4) nums.push(0, 1, 2, 3, 4, -1, n - 1);
    else if (page > n - 5) nums.push(0, -1, n - 5, n - 4, n - 3, n - 2, n - 1);
    else nums.push(0, -1, page - 1, page, page + 1, -1, n - 1);
    return btn(page - 1, '‹ zurück', false, 'nav') + btn(page + 1, 'weiter ›', false, 'nav') +
      nums.map(i => i < 0 ? '<span class="gap">…</span>' : btn(i, String(i + 1), i === page, 'num')).join('') +
      '<span class="dim"> Seite ' + (page + 1) + ' von ' + n + '</span>';
  }

  function draw() {
    $('grid').innerHTML = view.slice(page * PER, (page + 1) * PER).map(a => '<button class="tile' + (a.k === cur ? ' cur' : '') + '" data-k="' + esc(a.k) + '" title="' + esc(a.name + (who(a) ? ' – ' + who(a) : '')) + '">' +
      face(a, 'im', SM.favHtml('album', a.k, { name: a.name, artist: who(a), cls: 'oncover' })) + '<div class="nm">' + esc(a.name) + '</div><div class="ar">' + esc(who(a)) + (a.year ? ' · ' + a.year : '') + '</div><div class="ct">' +
      (area() && cnt(a) !== a.n ? cnt(a) + ' von ' : '') + a.n + ' Lied' + (a.n === 1 ? '' : 'er') + (a.plays ? ' · ' + a.plays + '× gespielt' : '') + '</div></button>').join('') ||
      '<div class="dim">Keine Alben gefunden.</div>';
    $('pgtop').innerHTML = $('pgbot').innerHTML = pager();
    $('single').classList.toggle('on', single);
    $('favonly').classList.toggle('on', favOnly);
    $('smp').value = smp;
    const L = '#ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
    $('letters').innerHTML = '<button data-l=""' + (letter ? '' : ' class="on"') + '>alle</button>' + L.map(c => '<button data-l="' + c + '"' + (letter === c ? ' class="on"' : '') + '>' + c + '</button>').join('');
  }

  // ---- ein Album ----
  async function open(k) {
    cur = k;
    history.replaceState(null, '', '#k=' + encodeURIComponent(k));
    draw();
    const a = all.find(x => x.k === k) || { k, name: '', n: 0, plays: 0, cover: '' };
    $('det').hidden = false;
    if (window.innerWidth <= 820) $('det').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('det').innerHTML = head(a) + '<div id="songs" class="dim">Lade die Lieder …</div><div id="tl" class="dim">Lade die Titelliste …</div>';
    let d = null;
    try { d = await (await fetch('/api/sm/album?k=' + encodeURIComponent(k))).json(); } catch (e) { $('songs').textContent = e.message; return; }
    if (cur !== k) return;
    const songs = curSongs = d.songs || [];
    const discs = new Set(songs.map(s => s.disc || 0)).size > 1;
    let lastDisc = -1;
    $('songs').className = '';
    $('songs').innerHTML = songs.map((s, i) => {
      const dh = discs && s.disc !== lastDisc ? '<div class="disc">' + (s.disc ? 'CD ' + s.disc : 'weitere Lieder (ohne CD-Ordner)') + '</div>' : '';
      lastDisc = s.disc;
      return dh + '<div class="song"><button class="pb" data-play="' + esc(s.path || '') + '" data-name="' + esc((s.artist || '') + ' - ' + (s.name || s.title || '')) + '"' + (s.path ? '' : ' disabled') + '>▶</button>' +
        '<button class="pb nx" data-nx="' + i + '" title="Als Nächstes spielen (kommt im Auto-DJ als nächstes Lied in die Playlist)" aria-label="Als Nächstes spielen"><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M6.3 4.9v6.2L11.2 8z" fill="currentColor"/></svg></button>' +
        '<img class="cvimg" data-tag="' + i + '" loading="lazy" alt="" title="Antippen: Tag bearbeiten" src="/api/sm/cover?p=' + encodeURIComponent(s.path || '') + '" onerror="this.style.visibility=&quot;hidden&quot;">' +
        '<div><div class="t"><span class="no">' + (parseInt(s.track, 10) || '') + '</span> ' + SM.favHtml('song', s.path || '', { cls: 'sm' }) + esc(s.name || s.title || '') + ' ' + (s.path ? SM.starsHtml(s.path, s.rating) : '') + '</div><div class="s">' +
        (s.artist ? '<a class="lnk" href="/musik/interpreten?n=' + encodeURIComponent(s.artist) + '">' + esc(s.artist) + '</a>' : '') + esc([s.genre, s.bpm ? Math.round(s.bpm) + ' BPM' : ''].filter(Boolean).map(x => ' · ' + x).join('')) + '</div></div>' +
        '<span class="p" title="' + (s.lastp ? 'zuletzt ' + dateTxt(s.lastp) : '') + '">' + (s.plays ? s.plays + '×' : '') + '</span></div>';
    }).join('') || '<div class="dim">Keine Lieder.</div>';
    if ($('badj')) $('badj').disabled = !songs.length;          // Auto-DJ: erst wenn die Lieder da sind
    if ($('bstars')) $('bstars').disabled = !songs.length;
    drawSongsBtns();
    loadInfo(k, false);
  }

  function head(a) {
    const art = a.sampler ? 'Verschiedene Interpreten' : a.artist ? '<a class="lnk" href="/musik/interpreten?n=' + encodeURIComponent(a.artist) + '">' + esc(a.artist) + '</a>' : '';
    return '<div class="hd">' + face(a, 'big') + '<div style="min-width:0"><h2 id="ahn"><span id="aname">' + esc(a.name) + '</span>' + SM.favHtml('album', a.k, { name: a.name, artist: who(a), cls: 'hbig' }) +
      '<button class="pen" data-a="aedit" title="Albumname ändern (wird in alle MP3s dieses Albums geschrieben)" aria-label="Albumname ändern">✎</button></h2>' +
      '<div class="meta">' + art + '</div><div class="meta">' + [a.year || '', a.n + ' Lied' + (a.n === 1 ? '' : 'er'), a.plays ? a.plays + '× gespielt' : '', a.last ? 'zuletzt ' + dateTxt(a.last) : ''].filter(Boolean).map(esc).join(' · ') + '</div>' +
      '<div class="meta" id="ainf"></div>' +
      '<div class="acts"><a class="btn" href="/musik?q=' + encodeURIComponent(a.name) + '">In Musik-DB zeigen</a><button data-a="adj" id="badj" disabled title="Alle Lieder dieser Liste hinten an die Playlist des Auto-DJ anhängen (was schon drin ist, kommt nicht doppelt)">Alle in den Auto-DJ</button><button data-a="stars" id="bstars" disabled title="Allen Liedern dieses Albums dieselben Sterne geben (kommen beim nächsten Start der Mixxx-App in Mixxx)">Alle ★ …</button></div></div></div>';
  }

  // Deezer: Datum, Label, Titelliste mit "hast du / fehlt" (am Pi 90 Tage gemerkt)
  async function loadInfo(k, refresh) {
    let d = null;
    if (!loadInfo.mk) loadInfo.mk = SM.missLoad();       // Merkliste Fehlt mir: welche schon gemerkt sind
    await loadInfo.mk;
    try { d = await SM.cmd('album_info', { k, refresh }); } catch (e) { if (cur === k && $('tl')) $('tl').textContent = 'Titelliste geht gerade nicht: ' + e.message; return; }
    if (cur !== k || !$('tl')) return;
    $('tl').className = '';
    if (!d.found) { $('tl').innerHTML = '<div class="dim">Deezer kennt dieses Album nicht (oder unter anderem Namen). <button class="lnk" data-a="info">neu suchen</button></div>'; return; }
    $('ainf').textContent = [d.date ? 'erschienen ' + d.date.split('-').reverse().join('.') : '', d.label].filter(Boolean).join(' · ');
    const a = all.find(x => x.k === k);
    if (d.cover && a && !document.querySelector('#det .big img[src*="/api/sm/cover"]:not([style*="hidden"])')) {
      const big = document.querySelector('#det .big');                                   // ohne eigenes Cover: das von Deezer zeigen
      if (big) big.innerHTML = '<img class="cvimg" data-zoom="500" alt="" src="' + esc(d.cover) + '">';
    }
    const discs = new Set(d.tracks.map(t => t.disc)).size > 1;
    let ld = -1;
    $('tl').innerHTML = '<div class="sum"><b>Titelliste laut Deezer</b> (' + esc(d.title) + (d.artist ? ', ' + esc(d.artist) : '') + '): ' + d.nb + ' Titel, ' +
      (d.missing ? '<span style="color:#ffd38a">dir fehlen ' + d.missing + '</span>' : '<span style="color:#8fe0a5">du hast alle</span>') + '</div>' +
      d.tracks.map(t => { const dh = discs && t.disc !== ld ? '<div class="disc">CD ' + t.disc + '</div>' : ''; ld = t.disc;
        return dh + '<div class="tr' + (t.have ? '' : ' miss') + '"><span class="' + (t.have ? 'ok' : 'no2') + '">' + (t.have ? '✓' : '–') + '</span><span class="no">' + (t.no || '') + '</span><span>' + esc(t.title) +
          (d.artist && t.artist && SM.artistKey(t.artist) !== SM.artistKey(d.artist) ? ' <span class="dim">· ' + esc(t.artist) + '</span>' : '') + '</span>' +
          (t.have ? '' : spotify(t.title, t.artist || d.artist) + SM.missBtn({ a: t.artist || d.artist || '', t: t.title, al: d.title || '' })) + '</div>'; }).join('') +
      '<div class="dim" style="font-size:11px;margin-top:6px">Quelle: Deezer · <button class="lnk" data-a="info">neu laden</button></div>';
  }

  // Fehlende Titel auf Spotify anhoeren (Wunsch 14.11.2026): Suche mit Titel und Interpret; am iPad/Mac oeffnet der Link die
  // Spotify im Browser, in einem eigenen Fenster "lb_spotify" (Wunsch 14.11.2026: zurueck in denselben Tab laedt sonst alles
  // neu; jedes weitere Lied kommt in dasselbe Fenster). Es geht nur der Suchtext hin.
  function spotify(title, artist) {
    const q = [title, artist].filter(Boolean).join(' ');
    return ' ' + SM.spotifyLink(q, '', 'Auf Spotify anhören: ' + q);
  }

  // Albumname in allen MP3s dieses Albums aendern (Bleistift neben dem Namen, Wunsch 14.11.2026). Schreibt der Musik-Rechner
  // (genre_edit.set_album, music_serve /genres op album), mit Protokoll und Zuruecknehmen wie beim Interpreten.
  function editName() {
    const h = $('ahn'), a = all.find(x => x.k === cur);
    if (!h || !a || h.querySelector('input')) return;
    const old = a.name;
    const box = document.createElement('div');
    box.className = 'aed';
    box.innerHTML = '<input id="aeinp" type="text" maxlength="200" autocomplete="off" spellcheck="false"><button id="aeok">Schreiben</button><button id="aeno">Abbrechen</button>';
    h.hidden = true;
    h.after(box);
    const inp = $('aeinp');
    inp.value = old;
    inp.focus();
    const close = () => { box.remove(); h.hidden = false; };
    $('aeno').onclick = close;
    inp.onkeydown = e => { if (e.key === 'Enter') $('aeok').click(); else if (e.key === 'Escape') close(); };
    $('aeok').onclick = async () => {
      const to = inp.value.replace(/ +/g, ' ').trim();
      if (!to) { SM.toast('Der Albumname darf nicht leer sein.', 4000); return; }
      if (to === old) { close(); return; }
      if (!await ensureMusic()) return;
      const songs = curSongs.filter(s => s.path), mp3 = songs.filter(s => /[.]mp3$/i.test(s.path)).length;
      if (!mp3) { SM.toast('Keine MP3 dabei: nur MP3s lassen sich schreiben.', 5000); return; }
      if (!await SM.ask('„' + old + '“ wird „' + to + '“ in ' + mp3 + ' MP3' + (mp3 === 1 ? '' : 's') + (mp3 < songs.length ? ' (' + (songs.length - mp3) + ' andere Dateien bleiben)' : '') +
        '. Nur das Feld Album ändert sich, die Musik bleibt gleich. Zurücknehmen geht hier oder im Genre-Editor (Protokoll). Schreiben?', undefined, 'Schreiben')) return;
      try {
        const r = await fetch(music + '/genres', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'album', paths: songs.map(s => s.path), to }) });
        const d = await r.json(); if (!r.ok || d.error) throw new Error(d.error || r.statusText);
      } catch (e) { SM.toast('Album ändern: ' + e.message, 7000); return; }
      box.innerHTML = '<span class="dim">Schreibe …</span>';
      $('aname').textContent = to;
      let st = null;
      for (let i = 0; i < 600; i++) {
        await new Promise(r => setTimeout(r, 1000));
        try { st = await (await fetch(music + '/genres?job=1&field=album')).json(); } catch (e) { continue; }
        const j = st.job || {};
        box.innerHTML = '<span class="dim">Schreibe: ' + (j.done || 0) + ' von ' + (j.total || mp3) + ' …</span>';
        if (j.state === 'done') break;
      }
      const j = (st && st.job) || {}, op = ((st && st.ops) || [])[0];
      h.hidden = false;
      box.className = 'meta';
      box.innerHTML = esc((j.ok || 0) + ' MP3' + (j.ok === 1 ? '' : 's') + ' geschrieben' + (j.skip ? ', ' + j.skip + ' übersprungen' + (j.gone ? ' (' + j.gone + ' fehlen am Stick)' : '') : '') + (j.err ? ' · ' + j.err : '') +
        '. Die Liste passt sich an, sobald der Musik-Rechner sie neu schickt.') + (op && !op.undone ? ' <button class="lnk" data-undo="' + esc(op.id) + '">Zurücknehmen</button>' : '');
      const ub = box.querySelector('[data-undo]');
      if (ub) ub.onclick = async () => {
        try {
          const r = await fetch(music + '/genres', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'undo', id: ub.dataset.undo }) });
          const d = await r.json(); if (!r.ok || d.error) throw new Error(d.error || r.statusText);
          box.textContent = 'Wird zurückgenommen … der alte Name kommt wieder in die Dateien.';
          $('aname').textContent = old;
        } catch (e) { SM.toast('Zurücknehmen: ' + e.message, 7000); }
      };
      const p0 = songs[0].path, keep = cur;
      for (const ms of [5000, 20000, 60000]) setTimeout(async () => {     // neu laden; das Album findet sich ueber sein erstes Lied
        if (cur !== keep) return;
        try {
          all = ((await (await fetch('/api/sm/albums')).json()) || {}).albums || all; filter(true);
          const d = await (await fetch('/api/sm/album?p=' + encodeURIComponent(p0))).json();
          const na = d.k && all.find(x => x.k === d.k);
          if (na && na.name === to && cur === keep) { cur = d.k; history.replaceState(null, '', '#k=' + encodeURIComponent(d.k)); $('aname').textContent = na.name; draw(); }
        } catch (e) { /* naechster Versuch */ }
      }, ms);
    };
  }

  // ---- Vorhoeren, Tag bearbeiten ----
  function drawSongsBtns() {
    document.querySelectorAll('#songs button[data-play]').forEach(b => { const on = b.dataset.play === playing && !audio.paused; b.classList.toggle('on', on); b.textContent = on ? '❚❚' : '▶'; });
  }
  async function ensureMusic() {
    if (!music) { try { music = ((await (await fetch('/api/musik/mac')).json()) || {}).music || ''; } catch (e) { music = ''; } }
    if (!music) SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer?).', 5000);
    return !!music;
  }
  async function play(p, name) {
    if (!await ensureMusic()) return;
    if (playing === p && !audio.paused) { audio.pause(); drawSongsBtns(); return; }
    if (playing !== p) { audio.src = music + '/audio?p=' + encodeURIComponent(p); playing = p; }
    try { await audio.play(); bar.show(name); } catch (e) { SM.toast('Abspielen: ' + e.message, 5000); }
    drawSongsBtns();
  }
  audio.addEventListener('pause', drawSongsBtns);
  audio.addEventListener('play', drawSongsBtns);

  // ---- Bedienung ----
  $('grid').addEventListener('click', e => { const t = e.target.closest('.tile'); if (t) open(t.dataset.k); });
  $('det').addEventListener('click', async e => {
    const im = e.target.closest('img[data-tag]');
    if (im) {
      const s = curSongs[+im.dataset.tag];
      if (s && s.path && await ensureMusic()) SM.tagEdit({ path: s.path, dur: s.dur || 0 }, music, () => { const k = cur; setTimeout(() => open(k), 600); });
      return;
    }
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.a === 'info') { $('tl').textContent = 'Lade die Titelliste …'; loadInfo(cur, true); return; }
    if (b.dataset.a === 'aedit') { editName(); return; }
    if (b.dataset.a === 'adj') { SM.autodjAdd(curSongs, false, 'Album'); return; }   // alle hinten an die Playlist (14.11.2026)
    if (b.dataset.a === 'stars') { const n = await SM.starsPick(b); if (n !== null) SM.starSet(curSongs.map(s => s.path), n); return; }
    if (b.dataset.nx != null) { SM.autodjAdd([curSongs[+b.dataset.nx]], true); return; }
    if (b.dataset.play) play(b.dataset.play, b.dataset.name);
  });
  $('letters').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { letter = b.dataset.l; filter(); } });
  $('q').addEventListener('input', () => { clearTimeout($('q')._t); $('q')._t = setTimeout(filter, 200); });
  $('sort').onchange = filter;
  $('smp').onchange = () => { smp = $('smp').value; store('alb_smp', smp); filter(); };
  $('single').onclick = () => { single = !single; store('alb_single', single ? '1' : '0'); filter(); };
  $('favonly').onclick = () => { favOnly = !favOnly; filter(); };
  document.addEventListener('s2lfav', () => { if (favOnly || $('sort').value === 'fav') filter(true); });
  $('areab').onclick = () => { $('areap').hidden = !$('areap').hidden; };
  $('aclose').onclick = () => { $('areap').hidden = true; };
  document.addEventListener('click', e => { if (!$('areap').hidden && !e.target.closest('.areaw')) $('areap').hidden = true; });
  $('areal').addEventListener('change', () => { areaSel = [...document.querySelectorAll('#areal input:checked')].map(i => i.value); store('alb_areas', JSON.stringify(areaSel)); areaLabel(); filter(); });
  $('aall').onclick = () => { areaSel = [...document.querySelectorAll('#areal input')].map(i => i.value); store('alb_areas', JSON.stringify(areaSel)); areas(); filter(); };
  $('anone').onclick = () => { areaSel = []; store('alb_areas', '[]'); areas(); filter(); };
  for (const id of ['pgtop', 'pgbot']) $(id).addEventListener('click', e => {
    const b = e.target.closest('button[data-pg]'); if (!b || b.disabled) return;
    page = +b.dataset.pg; draw();
    if (id === 'pgbot') $('pgtop').scrollIntoView({ block: 'start' });
  });
  load();
})();
