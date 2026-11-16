// Interpreten (Wunsch von Markus, 13.11.2026): Kacheln mit Bild, Klick zeigt Bild, Zahlen und Lieder des Interpreten.
// Daten vom Pi (showman/artists.py): /api/sm/artists, /api/sm/artist?k=, Bilder /api/sm/artist_img?k=&v=.
// Bilder holen, aendern, eigenes, entfernen und der Vorab-Lauf ueber /api/sm/cmd (artist_*, artists_bulk*).
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const PER = 60;                                     // Wunsch 13.11.2026: halb so viele je Seite
  let alias = {}, all = [], view = [], page = 0, cur = '', letter = '', music = '', bulkTimer = null, curSongs = [];
  const audio = new Audio();
  let playing = '';
  const bar = SM.playBar(audio, { onclose: () => { audio.pause(); playing = ''; drawSongsBtns(); } });
  let single = false, noImg = false, favOnly = false, areaSel = [];   // Bereiche: ["d:KLASSIK", "g:Après-Ski", ...], leer = alle (mehrere, 13.11.2026)
  try {
    single = localStorage.getItem('art_single') === '1';
    const v = JSON.parse(localStorage.getItem('art_areas') || 'null');
    areaSel = Array.isArray(v) ? v.filter(x => typeof x === 'string') : (localStorage.getItem('art_area') ? [localStorage.getItem('art_area')] : []);
  } catch (e) { /* privates Fenster */ }
  const saveAreas = () => { try { localStorage.setItem('art_areas', JSON.stringify(areaSel)); } catch (e) { /* egal */ } };

  // Platzhalter ohne Bild: Anfangsbuchstaben auf einer Farbe, die am Namen haengt (immer dieselbe)
  const COLORS = [['#3b2d5c', '#c9b8ff'], ['#1f4d4a', '#8fe0d5'], ['#5c3a1f', '#ffc68f'], ['#1e3a5c', '#9fd0ff'], ['#4d1f3a', '#ffa3cf'], ['#2f4d1f', '#b7e88f']];
  const color = k => { let h = 0; for (const c of k) h = (h * 31 + c.charCodeAt(0)) >>> 0; return COLORS[h % COLORS.length]; };
  const initials = n => { const w = String(n).replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/).filter(Boolean); return ((w[0] || '?')[0] + (w.length > 1 ? w[1][0] : '')).toUpperCase(); };
  const imgUrl = a => '/api/sm/artist_img?k=' + encodeURIComponent(a.k) + '&v=' + a.img;
  const face = (a, cls, extra) => {
    if (a.img) return '<div class="' + cls + '"><img loading="lazy" alt=""' + (cls === 'big' ? ' class="cvimg" data-zoom="500"' : '') + ' src="' + imgUrl(a) + '">' + (extra || '') + '</div>';
    const [bg, fg] = color(a.k);
    return '<div class="' + cls + (a.none ? ' noimg' : '') + '" style="' + (a.none ? '' : 'background:' + bg + ';color:' + fg) + '">' + esc(initials(a.name)) + (extra || '') + '</div>';
  };
  const letterOf = a => { const c = SM.artistKey(a.name)[0] || '#'; return /[a-z]/.test(c) ? c.toUpperCase() : '#'; };
  const dateTxt = s => s ? new Date(s * 1000).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '';

  async function load() {
    try {
      SM.favLoad();                                    // Herzen (Favoriten, 14.11.2026)
      const d = await (await fetch('/api/sm/artists')).json();
      all = d.artists || [];
      alias = d.alias || {};
      music = d.music || music;
    } catch (e) { $('astat').textContent = 'Konnte die Interpreten nicht laden: ' + e.message; return; }
    areas();
    filter(true);                                      // Auffrischen (Vorab-Lauf) bleibt auf der Seite (Fehlerbericht 13.11.2026)
    const m = /k=([^&]+)/.exec(location.hash) || /[?&]k=([^&]+)/.exec(location.search);
    const n = new URLSearchParams(location.search).get('n');
    let want = m ? decodeURIComponent(m[1]) : n ? SM.artistKey(n) : '';
    want = alias[want] || want;                        // "Rainhard Fendrich & Vienna Symphony Orchestra" -> Rainhard Fendrich
    if (want && !cur) open(want);
  }

  // Bereich (Wunsch 13.11.2026): oberster Ordner im Musikordner ("d:KLASSIK") oder Gruppe im Tag ("g:Après-Ski"), mit Zahl der Interpreten
  // Lieder eines Interpreten in den gewaehlten Bereichen (hoechstens alle; ein Lied kann in Ordner und Gruppe zugleich zaehlen)
  const inArea = a => !areaSel.length ? a.n : Math.min(a.n, areaSel.reduce((s, v) => s + (((v[0] === 'd' ? a.dirs : a.grps) || {})[v.slice(2)] || 0), 0));
  // Genre (Wunsch 13.11.2026): Lieder des Eintrags in den gewaehlten Genres; zusammen mit dem Bereich zaehlt das Kleinere
  const genP = SM.checkPicker($('genb'), { name: 'Genre', key: 'art_genres', onChange: () => filter() });
  const inGenre = a => !genP.sel.length ? a.n : Math.min(a.n, genP.sel.reduce((s, g) => s + ((a.gens || {})[g] || 0), 0));
  const cnt = a => Math.min(inArea(a), inGenre(a));
  const area = () => areaSel.length > 0 || genP.sel.length > 0;
  function areas() {
    const D = {}, G = {};
    for (const a of all) { for (const d in a.dirs || {}) D[d] = (D[d] || 0) + 1; for (const g in a.grps || {}) G[g] = (G[g] || 0) + 1; }
    const known = new Set([...Object.keys(D).map(d => 'd:' + d), ...Object.keys(G).map(g => 'g:' + g)]);
    if (all.length) areaSel = areaSel.filter(v => known.has(v));   // Bereiche, die es nicht mehr gibt, fallen weg
    const opt = (v, t, n) => '<label><input type="checkbox" value="' + esc(v) + '"' + (areaSel.includes(v) ? ' checked' : '') + '> ' + esc(t) + '<span class="n">' + n + '</span></label>';
    const abc = o => Object.keys(o).sort((x, y) => x.localeCompare(y, 'de'));
    const h = (Object.keys(D).length ? '<div class="ag">Ordner (Zahl der Interpreten)</div>' + abc(D).map(d => opt('d:' + d, d, D[d])).join('') : '') +
      (Object.keys(G).length ? '<div class="ag">Gruppe im Tag</div>' + abc(G).map(g => opt('g:' + g, g, G[g])).join('') : '') || '<div class="dim">Keine Bereiche bekannt.</div>';
    if ($('areal').dataset.h !== h) { $('areal').innerHTML = h; $('areal').dataset.h = h; }
    const GE = {};
    for (const a of all) for (const g in a.gens || {}) GE[g] = (GE[g] || 0) + 1;
    genP.render([{ title: 'Genre (Zahl der Interpreten)', items: Object.keys(GE).sort((x, y) => x.localeCompare(y, 'de', { sensitivity: 'base' })).map(g => ({ v: g, t: g, n: GE[g] })) }]);   // Auffrischen: offene Liste nicht neu bauen
    areaLabel();
  }
  function areaLabel() {
    const n = areaSel.length, nm = v => v.slice(2);
    $('areab').textContent = 'Bereich: ' + (!n ? 'alle' : n <= 2 ? areaSel.map(nm).join(', ') : nm(areaSel[0]) + ' + ' + (n - 1) + ' weitere') + ' ▾';
    $('areab').classList.toggle('on', n > 0);
  }

  function filter(keep) {
    const q = SM.artistKey($('q').value).replace(/-/g, ' ').trim(), srt = $('sort').value;
    view = all.filter(a => cnt(a) > 0 && (single || favOnly || cnt(a) > 1 || area() || a.k === cur) && (!noImg || !a.img) && (!favOnly || SM.favOf('artist', a.k)) && (!letter || letterOf(a) === letter) &&
      (!q || a.k.replace(/-/g, ' ').includes(q)));
    const by = { fav: (a, b) => SM.favOf('artist', b.k) - SM.favOf('artist', a.k) || cnt(b) - cnt(a), n: (a, b) => cnt(b) - cnt(a), plays: (a, b) => b.plays - a.plays || b.n - a.n, last: (a, b) => b.last - a.last || b.n - a.n };
    view.sort((a, b) => (by[srt] ? by[srt](a, b) : 0) || a.k.localeCompare(b.k));
    const withImg = all.filter(a => a.img).length, singles = all.filter(a => a.n === 1).length;
    $('astat').innerHTML = '<b>' + all.length + '</b> Interpreten · <b>' + withImg + '</b> mit Bild · ' + (all.length - withImg) + ' ohne' +
      (single || area() ? '' : ' · ' + singles + ' mit nur einem Lied ausgeblendet') + (view.length !== all.length ? ' · gezeigt: ' + view.length : '');
    if (!keep) page = 0;
    page = Math.max(0, Math.min(page, Math.ceil(view.length / PER) - 1));
    draw();
  }

  function pager() {
    const n = Math.ceil(view.length / PER);
    if (n <= 1) return '';
    const btn = (p, t, on, cls) => '<button data-pg="' + p + '" class="' + (cls || '') + (on ? ' on' : '') + '"' + (p < 0 || p >= n ? ' disabled' : '') + '>' + t + '</button>';
    // immer gleich viele Felder (Fehlerbericht 13.11.2026: "weiter" huepfte, wenn die Punkte kamen und gingen); zurueck und weiter vorne
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
    $('grid').innerHTML = view.slice(page * PER, (page + 1) * PER).map(a => '<button class="tile' + (a.k === cur ? ' cur' : '') + '" data-k="' + esc(a.k) + '" title="' + esc(a.name) + '">' +
      face(a, 'im', SM.favHtml('artist', a.k, { name: a.name, cls: 'oncover' })) + '<div class="nm">' + esc(a.name) + '</div><div class="ct">' + (area() && cnt(a) !== a.n ? cnt(a) + ' von ' : '') + a.n + ' Lied' + (a.n === 1 ? '' : 'er') + (a.plays ? ' · ' + a.plays + '× gespielt' : '') + '</div></button>').join('') ||
      '<div class="dim">Keine Interpreten gefunden.</div>';
    $('pgtop').innerHTML = $('pgbot').innerHTML = pager();
    $('single').classList.toggle('on', single);
    $('noimg').classList.toggle('on', noImg);
    $('favonly').classList.toggle('on', favOnly);
    const L = '#ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
    $('letters').innerHTML = '<button data-l=""' + (letter ? '' : ' class="on"') + '>alle</button>' + L.map(c => '<button data-l="' + c + '"' + (letter === c ? ' class="on"' : '') + '>' + c + '</button>').join('');
  }

  // ---- ein Interpret ----
  async function open(k) {
    cur = k;
    history.replaceState(null, '', '#k=' + encodeURIComponent(k));
    draw();
    const a = all.find(x => x.k === k) || { k, name: k, n: 0, plays: 0, img: 0 };
    $('det').hidden = false;
    if (window.innerWidth <= 820) $('det').scrollIntoView({ behavior: 'smooth', block: 'start' });   // Handy: Bild und Lieder stehen oben
    $('det').innerHTML = head(a) + '<div id="myalb"></div><div id="ainfo" class="dim">Lade Infos …</div><div id="songs" class="dim">Lade die Lieder …</div>';
    loadInfo(k, false);
    myAlbums(k);
    let d = null;
    try { d = await (await fetch('/api/sm/artist?k=' + encodeURIComponent(k))).json(); } catch (e) { $('songs').textContent = e.message; return; }
    if (cur !== k) return;
    const songs = curSongs = (d.songs || []).slice().sort((x, y) => (y.plays || 0) - (x.plays || 0) || String(x.name || x.title).localeCompare(String(y.name || y.title)));
    $('songs').className = '';
    $('songs').innerHTML = songs.map((s, i) => '<div class="song"><button class="pb" data-play="' + esc(s.path || '') + '" data-name="' + esc((s.artist || '') + ' - ' + (s.name || s.title || '')) + '"' + (s.path && music ? '' : ' disabled') + '>▶</button>' +
      '<button class="pb nx" data-nx="' + i + '" title="Als Nächstes spielen (kommt im Auto-DJ als nächstes Lied in die Playlist)" aria-label="Als Nächstes spielen"><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M6.3 4.9v6.2L11.2 8z" fill="currentColor"/></svg></button>' +
      '<img class="cvimg" data-tag="' + i + '" loading="lazy" alt="" title="Antippen: Tag bearbeiten" src="/api/sm/cover?p=' + encodeURIComponent(s.path || '') + '" onerror="this.style.visibility=&quot;hidden&quot;">' +
      '<div><div class="t">' + SM.favHtml('song', s.path || '', { cls: 'sm' }) + esc(s.name || s.title || '') + ' ' + (s.path ? SM.starsHtml(s.path, s.rating) : '') + '</div><div class="s">' + esc([s.album, s.year || '', s.genre, s.bpm ? Math.round(s.bpm) + ' BPM' : ''].filter(Boolean).join(' · ')) +
      (s.artist && SM.artistMain(s.artist) !== a.name ? ' · <i>' + esc(s.artist) + '</i>' : '') + '</div></div>' +
      '<span class="p" title="' + (s.lastp ? 'zuletzt ' + dateTxt(s.lastp) : '') + '">' + (s.plays ? s.plays + '×' : '') + '</span></div>').join('') || '<div class="dim">Keine Lieder.</div>';
    if ($('badj')) $('badj').disabled = !songs.length;          // Auto-DJ: erst wenn die Lieder da sind (ausgegraut statt versteckt)
    if ($('bstars')) $('bstars').disabled = !songs.length;
    drawSongsBtns();
  }

  // Infos aus dem Internet (TheAudioDB: Lebenslauf, Jahre, Herkunft; Deezer: Alben), am Pi 90 Tage gemerkt
  async function loadInfo(k, refresh) {
    let d = null;
    try { d = await SM.cmd('artist_info', { k, refresh }); } catch (e) { if (cur === k && $('ainfo')) $('ainfo').textContent = 'Infos gehen gerade nicht: ' + e.message; return; }
    if (cur !== k || !$('ainfo')) return;
    const facts = [d.born && d.members <= 1 ? 'geboren ' + d.born : '', d.formed && (d.members > 1 || !d.born) ? 'gegründet ' + d.formed : '',
      d.died ? 'gestorben ' + d.died : '', d.members > 1 ? d.members + ' Mitglieder' : '', d.place, [d.genre, d.style].filter(Boolean).join(', ')].filter(Boolean);
    const bio = String(d.bio || '');
    $('ainfo').className = 'info';
    $('ainfo').innerHTML = (facts.length ? '<div class="facts">' + esc(facts.join(' · ')) + '</div>' : '') +
      (bio ? '<div class="bio' + (bio.length > 420 ? ' short' : '') + '">' + esc(bio).replace(/\n\s*\n/g, '<br><br>') + '</div>' +
        (bio.length > 420 ? '<button class="lnk" data-a="bio">mehr lesen</button>' : '') + (d.lang === 'en' ? ' <span class="dim">(nur auf Englisch vorhanden)</span>' : '') : '') +
      (d.web ? ' <a class="lnk" href="' + esc(d.web) + '" rel="noopener">Webseite ↗</a>' : '') +
      ((d.albums || []).length ? '<div class="alh">Alben laut Deezer (' + d.n_albums + ')</div><div class="albums">' + d.albums.map(x => '<div class="alb" title="' + esc(x.title + (x.year ? ' (' + x.year + ')' : '')) + '">' +
        (x.cover ? '<img loading="lazy" alt="" src="' + esc(x.cover) + '">' : '<div class="noc"></div>') + '<div class="at mq"><span>' + esc(x.title) + '</span></div><div class="ay">' + esc(x.year || '') + '</div></div>').join('') + '</div>' : '') +
      (!facts.length && !bio && !(d.albums || []).length ? '<div class="dim">Keine Infos gefunden.</div>' : '') +
      '<div class="src">Quellen: TheAudioDB, Deezer · <button class="lnk" data-a="info">neu laden</button></div>';
    SM.marquee($('ainfo'));
  }

  // Alben dieses Interpreten in deiner Sammlung (Seite Alben, 13.11.2026)
  let albCache = null;
  async function myAlbums(k) {
    if (!albCache) { try { albCache = ((await (await fetch('/api/sm/albums')).json()) || {}).albums || []; } catch (e) { albCache = []; } }
    if (cur !== k || !$('myalb')) return;
    const mine = albCache.filter(x => x.artist_k === k).sort((x, y) => (x.year || 9999) - (y.year || 9999));
    $('myalb').innerHTML = mine.length ? '<div class="alh" style="margin:10px 0 4px;color:var(--dim);font-size:12px">In deiner Sammlung: ' + mine.length + ' Album' + (mine.length === 1 ? '' : 'en') + '</div><div class="albums">' +
      mine.map(x => '<a class="alb" href="/musik/alben#k=' + encodeURIComponent(x.k) + '" title="' + esc(x.name) + '" style="color:inherit;text-decoration:none"><img loading="lazy" alt="" src="/api/sm/cover?p=' + encodeURIComponent(x.cover || '') +
        '" onerror="this.style.visibility=&quot;hidden&quot;"><div class="at mq"><span>' + esc(x.name) + '</span></div><div class="ay">' + (x.year || '') + ' · ' + x.n + ' Lied' + (x.n === 1 ? '' : 'er') + '</div></a>').join('') + '</div>' : '';
    SM.marquee($('myalb'));
  }

  function head(a) {
    return '<div class="hd">' + face(a, 'big') + '<div style="min-width:0"><h2>' + esc(a.name) + SM.favHtml('artist', a.k, { name: a.name, cls: 'hbig' }) + '</h2>' +
      '<div class="meta">' + a.n + ' Lied' + (a.n === 1 ? '' : 'er') + (a.plays ? ' · ' + a.plays + '× gespielt' : '') + (a.last ? ' · zuletzt ' + dateTxt(a.last) : '') + (a.genre ? ' · ' + esc(a.genre) : '') + '</div>' +
      '<div class="meta" id="imgsrc">' + (a.img ? 'Bild: ' + ({ deezer: 'Deezer', audiodb: 'TheAudioDB', eigen: 'eigenes', sicherung: 'aus der Sicherung' }[a.src] || '–') : a.none ? 'Kein Bild gefunden' : 'Noch kein Bild') + '</div>' +
      '<div class="acts"><button data-a="fetch">' + (a.img ? 'Bild neu suchen' : 'Bild suchen') + '</button><button data-a="pick">Bild ändern</button>' +
      (a.img ? '<button data-a="remove">Bild entfernen</button>' : '') + '<button data-a="rename" title="Den Interpreten in allen MP3s dieses Interpreten ändern oder leeren (etwa falsch getaggte Samples)">Interpret ändern …</button>' +
      '<a class="btn" href="/musik?q=' + encodeURIComponent(a.name) + '">In Musik-DB zeigen</a><button data-a="adj" id="badj" disabled title="Alle Lieder dieser Liste hinten an die Playlist des Auto-DJ anhängen (was schon drin ist, kommt nicht doppelt)">Alle in den Auto-DJ</button><button data-a="stars" id="bstars" disabled title="Allen Liedern dieser Liste dieselben Sterne geben (kommen beim nächsten Start der Mixxx-App in Mixxx)">Alle ★ …</button></div></div></div>';
  }

  function refreshOne(k, img, none) {
    const a = all.find(x => x.k === k);
    if (!a) return;
    a.img = img || 0;
    a.none = none ? 1 : 0;
    const box = document.querySelector('#det .hd');
    if (box && cur === k) { box.outerHTML = head(a); if ($('badj')) $('badj').disabled = !curSongs.length; if ($('bstars')) $('bstars').disabled = !curSongs.length; }
    bulk();
    filter(true);                                      // Zahlen oben (mit Bild / ohne) neu, Seite bleibt
  }

  async function act(what) {
    const k = cur, a = all.find(x => x.k === k);
    if (!a) return;
    try {
      if (what === 'fetch') {
        SM.toast('Suche ein Bild für ' + a.name + ' …', 2000);
        const d = await SM.cmd('artist_fetch', { k });
        if (d.ok) { a.src = 'deezer'; refreshOne(k, d.img, false); SM.toast('Bild gefunden.', 2500); }
        else { refreshOne(k, 0, true); SM.toast('Kein passendes Bild gefunden. „Bild ändern“ zeigt Vorschläge.', 5000); }
      } else if (what === 'remove') {
        if (!await SM.ask('Bild von „' + a.name + '“ entfernen? „Bilder für alle holen“ holt es danach nicht von selbst wieder.', undefined, 'Entfernen')) return;
        await SM.cmd('artist_remove', { k });
        refreshOne(k, 0, true);
      } else if (what === 'pick') pickDlg(a);
      else if (what === 'rename') renameArtist(a);
    } catch (e) { SM.toast(e.message, 6000); }
  }

  // Interpret in allen MP3s aendern oder leeren (Wunsch 13.11.2026, etwa "Konrad" bei den Samples). Schreibt der Musik-Rechner
  // (genre_edit.set_artist, music_serve /genres op artist), mit Protokoll und Zuruecknehmen wie im Genre-Editor.
  async function renameArtist(a) {
    if (!music) { try { music = ((await (await fetch('/api/musik/mac')).json()) || {}).music || ''; } catch (e) { music = ''; } }
    if (!music) { SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer?).', 5000); return; }
    const songs = curSongs.filter(s => s.path), mp3 = songs.filter(s => /\.mp3$/i.test(s.path)).length;
    if (!mp3) { SM.toast('Keine MP3 dabei: nur MP3s lassen sich schreiben.', 5000); return; }
    const to = await SM.ask('Neuer Interpret für „' + a.name + '“ in ' + mp3 + ' MP3' + (mp3 === 1 ? '' : 's') + (mp3 < songs.length ? ' (' + (songs.length - mp3) + ' andere Dateien bleiben)' : '') +
      '.\n\nLeer lassen entfernt den Interpreten. „feat. …“ hinter dem Namen bleibt.', a.name, 'Ändern');
    if (to === null || to.trim() === a.name) return;
    if (!await SM.ask((to.trim() ? '„' + a.name + '“ wird „' + to.trim() + '“' : 'Der Interpret „' + a.name + '“ wird entfernt') + ' in ' + mp3 + ' MP3' + (mp3 === 1 ? '' : 's') +
      '. Nur dieses Feld ändert sich, die Musik bleibt gleich. Zurücknehmen geht hier oder im Genre-Editor (Protokoll). Schreiben?', undefined, 'Schreiben')) return;
    const say = t => { const e = $('imgsrc'); if (e) e.textContent = t; };
    try {
      const r = await fetch(music + '/genres', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'artist', paths: songs.map(s => s.path), old: a.name, to: to.trim() }) });
      const d = await r.json(); if (!r.ok || d.error) throw new Error(d.error || r.statusText);
    } catch (e) { SM.toast('Interpret ändern: ' + e.message, 7000); return; }
    let st = null;
    for (let i = 0; i < 600; i++) {
      await new Promise(r => setTimeout(r, 1000));
      try { st = await (await fetch(music + '/genres?job=1')).json(); } catch (e) { continue; }
      const j = st.job || {};
      say('Schreibe: ' + (j.done || 0) + ' von ' + (j.total || mp3) + ' …');
      if (j.state === 'done') break;
    }
    const j = (st && st.job) || {}, op = ((st && st.artist_ops) || [])[0];
    const msg = (j.ok || 0) + ' MP3' + (j.ok === 1 ? '' : 's') + ' geschrieben' + (j.skip ? ', ' + j.skip + ' übersprungen' + (j.gone ? ' (' + j.gone + ' fehlen am Stick)' : '') : '') + (j.err ? ' · ' + j.err : '') +
      '. Die Liste passt sich an, sobald der Musik-Rechner sie neu schickt (meist in ein, zwei Minuten).';
    const box = document.createElement('div');
    box.className = 'meta';
    box.innerHTML = esc(msg) + (op && !op.undone ? ' <button class="lnk" data-undo="' + esc(op.id) + '">Zurücknehmen</button>' : '');
    const hd = document.querySelector('#det .hd > div:last-child'); if (hd) hd.appendChild(box);
    const ub = box.querySelector('[data-undo]');
    if (ub) ub.onclick = async () => {
      try {
        const r = await fetch(music + '/genres', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op: 'undo', id: ub.dataset.undo }) });
        const d = await r.json(); if (!r.ok || d.error) throw new Error(d.error || r.statusText);
        box.textContent = 'Wird zurückgenommen … die alten Namen kommen wieder in die Dateien.';
      } catch (e) { SM.toast('Zurücknehmen: ' + e.message, 7000); }
    };
    for (const ms of [5000, 20000, 60000]) setTimeout(load, ms);   // die Liste kommt vom Musik-Rechner meist in Sekunden, selten in einer Minute
  }

  function pickDlg(a) {
    const m = document.createElement('div');
    m.className = 'modal';
    m.innerHTML = '<div class="box pick"><h2>Bild für „' + esc(a.name) + '“</h2><p class="dim" style="margin:0">Antippen übernimmt das Bild. Die Vorschläge kommen von Deezer und TheAudioDB; dorthin geht nur der Name des Interpreten.</p>' +
      '<div class="sugs"><div class="dim">Suche Vorschläge …</div></div><div class="row" style="display:flex;gap:8px;flex-wrap:wrap"><button id="pkup">Eigenes Bild vom Rechner …</button><button id="pkx">Schließen</button></div></div>';
    document.body.appendChild(m);
    const close = () => m.remove();
    m.querySelector('#pkx').onclick = close;
    m.addEventListener('click', e => { if (e.target === m) close(); });
    m.querySelector('#pkup').onclick = () => { $('upfile').value = ''; $('upfile').onchange = () => upload(a, close); $('upfile').click(); };
    SM.cmd('artist_suggest', { k: a.k }).then(d => {
      const it = d.items || [];
      m.querySelector('.sugs').innerHTML = it.map((x, i) => '<button data-i="' + i + '"><img alt="" src="' + esc(x.url) + '">' + esc(x.label) + '</button>').join('') ||
        '<div class="dim">Keine Vorschläge gefunden. Nimm ein eigenes Bild.</div>';
      m.querySelectorAll('.sugs button').forEach(b => b.onclick = async () => {
        try {
          const r = await SM.cmd('artist_choose', { k: a.k, url: it[+b.dataset.i].url });
          a.src = it[+b.dataset.i].src;
          refreshOne(a.k, r.img, false);
          close();
        } catch (e) { SM.toast(e.message, 6000); }
      });
    }).catch(e => { m.querySelector('.sugs').innerHTML = '<div class="dim">Vorschläge gehen gerade nicht: ' + esc(e.message) + '</div>'; });
  }

  async function upload(a, done) {
    const f = $('upfile').files[0];
    if (!f) return;
    try {
      const url = await SM.squareCover(f, 800);
      const r = await SM.cmd('artist_upload', { k: a.k, data: url.split(',')[1] });
      a.src = 'eigen';
      refreshOne(a.k, r.img, false);
      if (done) done();
    } catch (e) { SM.toast('Bild: ' + e.message, 6000); }
  }

  // ---- Vorhoeren ----
  function drawSongsBtns() {
    document.querySelectorAll('#songs button[data-play]').forEach(b => { const on = b.dataset.play === playing && !audio.paused; b.classList.toggle('on', on); b.textContent = on ? '❚❚' : '▶'; });
  }
  async function play(p, name) {
    if (!music) { try { music = ((await (await fetch('/api/musik/mac')).json()) || {}).music || ''; } catch (e) { music = ''; } }
    if (!music) { SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer?).', 5000); return; }
    if (playing === p && !audio.paused) { audio.pause(); drawSongsBtns(); return; }
    if (playing !== p) { audio.src = music + '/audio?p=' + encodeURIComponent(p); playing = p; }
    try { await audio.play(); bar.show(name); } catch (e) { SM.toast('Abspielen: ' + e.message, 5000); }
    drawSongsBtns();
  }
  audio.addEventListener('pause', drawSongsBtns);
  audio.addEventListener('play', drawSongsBtns);

  // ---- Vorab-Lauf ----
  async function bulk(cmd) {
    let s = null;
    try { s = await SM.cmd(cmd ? 'artists_bulk' : 'artists_bulk_status', cmd ? { on: cmd === 'on' } : {}); } catch (e) { $('bulk').textContent = e.message; return; }
    $('bbulk').textContent = s.running ? 'Anhalten' : 'Bilder für alle holen';
    $('bretry').disabled = !!s.running || !s.none;      // ausgrauen statt verstecken
    $('bulk').textContent = s.running ? 'Holt Bilder: ' + s.done + ' von ' + s.total + ' haben eins, ' + s.none + ' ohne Treffer' + (s.current ? ' · gerade: ' + s.current : '') + (s.error ? ' · ' + s.error : '')
      : s.total ? s.done + ' von ' + s.total + ' Interpreten haben ein Bild' + (s.none ? ', bei ' + s.none + ' gab es keins' : '') + '. Eine Anfrage alle 3 Sekunden, läuft im Hintergrund weiter.' : '';
    clearTimeout(bulkTimer);
    if (s.running) bulkTimer = setTimeout(async () => { await bulk(); await load(); }, 8000);
  }
  $('bbulk').onclick = () => bulk($('bbulk').textContent === 'Anhalten' ? 'off' : 'on');
  $('bretry').onclick = async () => {                  // Leere noch einmal versuchen (14.11.2026)
    try {
      const d = await SM.cmd('artists_retry', {});
      SM.toast(d.retried ? d.retried + ' Interpreten ohne Bild werden noch einmal gesucht (einer alle 3 Sekunden, im Hintergrund).' : 'Keine erfolglosen Suchen offen. Der Lauf sucht nur noch neue Interpreten.', 5000);
    } catch (e) { SM.toast('Ging nicht: ' + e.message, 5000); }
    bulk();
  };

  // ---- Bedienung ----
  $('grid').addEventListener('click', e => { const t = e.target.closest('.tile'); if (t) open(t.dataset.k); });
  $('det').addEventListener('click', async e => {
    const im = e.target.closest('img[data-tag]');
    if (im) {                                         // Cover antippen: gleich "Tag bearbeiten" (Wunsch 13.11.2026)
      const s = curSongs[+im.dataset.tag];
      if (!music) { try { music = ((await (await fetch('/api/musik/mac')).json()) || {}).music || ''; } catch (x) { music = ''; } }
      if (!music) { SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer?).', 5000); return; }
      if (s && s.path) SM.tagEdit({ path: s.path, dur: s.dur || 0 }, music, () => { const k = cur; setTimeout(() => open(k), 600); });
      return;
    }
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.a === 'bio') { const x = document.querySelector('#ainfo .bio'); x.classList.toggle('short'); b.textContent = x.classList.contains('short') ? 'mehr lesen' : 'weniger'; return; }
    if (b.dataset.a === 'info') { $('ainfo').textContent = 'Lade Infos …'; loadInfo(cur, true); return; }
    if (b.dataset.a === 'adj') { SM.autodjAdd(curSongs, false, 'Interpret'); return; }   // alle hinten an die Playlist (14.11.2026)
    if (b.dataset.a === 'stars') { const n = await SM.starsPick(b); if (n !== null) SM.starSet(curSongs.map(s => s.path), n); return; }
    if (b.dataset.nx != null) { SM.autodjAdd([curSongs[+b.dataset.nx]], true); return; }
    if (b.dataset.a) act(b.dataset.a);
    else if (b.dataset.play) play(b.dataset.play, b.dataset.name);
  });
  $('letters').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { letter = b.dataset.l; filter(); } });
  $('q').addEventListener('input', () => { clearTimeout($('q')._t); $('q')._t = setTimeout(filter, 200); });
  $('sort').onchange = filter;
  $('areab').onclick = () => { $('areap').hidden = !$('areap').hidden; };
  $('aclose').onclick = () => { $('areap').hidden = true; };
  document.addEventListener('click', e => { if (!$('areap').hidden && !e.target.closest('.areaw')) $('areap').hidden = true; });
  $('areal').addEventListener('change', () => {
    areaSel = [...document.querySelectorAll('#areal input:checked')].map(i => i.value);
    saveAreas(); areaLabel(); filter();
  });
  $('aall').onclick = () => { areaSel = [...document.querySelectorAll('#areal input')].map(i => i.value); saveAreas(); areas(); filter(); };
  $('anone').onclick = () => { areaSel = []; saveAreas(); areas(); filter(); };
  $('single').onclick = () => { single = !single; try { localStorage.setItem('art_single', single ? '1' : '0'); } catch (e) { /* egal */ } filter(); };
  $('noimg').onclick = () => { noImg = !noImg; filter(); };
  $('favonly').onclick = () => { favOnly = !favOnly; filter(); };
  document.addEventListener('s2lfav', () => { if (favOnly || $('sort').value === 'fav') filter(true); });
  for (const id of ['pgtop', 'pgbot']) $(id).addEventListener('click', e => {
    const b = e.target.closest('button[data-pg]'); if (!b || b.disabled) return;
    page = +b.dataset.pg; draw();
    if (id === 'pgbot') $('pgtop').scrollIntoView({ block: 'start' });
  });
  load();
  bulk();
})();
