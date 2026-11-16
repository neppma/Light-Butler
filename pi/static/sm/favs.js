// Favoriten (Wunsch von Markus, 14.11.2026): alle Lieder, Alben, Interpreten und Genres mit Herz auf einer Seite.
// Daten vom Pi: /api/sm/favs_page (showman/favorites.py). Das Herz selbst kommt aus core.js (SM.favHtml, SM.favToggle).
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const STEP = 200;                                   // Lieder laufend nachladen, wenn man in der Spalte nach unten scrollt (kein Blaettern)
  let D = { songs: [], albums: [], artists: [], genres: [], all_genres: [] }, conf = {}, music = '', shown = 0, view = [], half = true;
  try { half = localStorage.getItem('fav_half') !== '0'; } catch (e) { /* privates Fenster */ }
  const audio = new Audio();
  let playing = '';
  const bar = SM.playBar(audio, { onclose: () => { audio.pause(); playing = ''; drawPlay(); } });
  const norm = s => String(s || '').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
  const COLORS = [['#3b2d5c', '#c9b8ff'], ['#1f4d4a', '#8fe0d5'], ['#5c3a1f', '#ffc68f'], ['#1e3a5c', '#9fd0ff'], ['#4d1f3a', '#ffa3cf'], ['#2f4d1f', '#b7e88f']];
  const color = k => { let h = 0; for (const c of String(k)) h = (h * 31 + c.charCodeAt(0)) >>> 0; return COLORS[h % COLORS.length]; };
  const initials = n => { const w = String(n).replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/).filter(Boolean); return ((w[0] || '?')[0] + (w.length > 1 ? w[1][0] : '')).toUpperCase(); };

  async function load() {
    try {
      const [d] = await Promise.all([SM.get('/api/sm/favs_page'), SM.favLoad()]);
      D = d; conf = d.conf || {}; music = d.music || music;
    } catch (e) { $('msg').textContent = 'Konnte die Favoriten nicht laden: ' + e.message; return; }
    draw(true);
  }

  const words = (...a) => norm(a.filter(Boolean).join(' '));
  function draw(keep) {
    const q = norm($('q').value).split(/\s+/).filter(Boolean);
    const hit = t => q.every(w => t.includes(w));
    // Lieder: eigenes Herz immer, halbes nur mit "auch halbe"; der Stand kommt aus SM.favOf (gleich nach einem Tipp)
    const st = s => SM.favOf('song', s.path);
    view = D.songs.filter(s => (st(s) === 2 || (half && st(s) === 1)) && hit(words(s.name, s.title, s.artist, s.album, s.genre)));
    const srt = $('ssort').value;
    const by = { t: (a, b) => (b.ft || 0) - (a.ft || 0), plays: (a, b) => (b.plays || 0) - (a.plays || 0), art: (a, b) => norm(a.artist).localeCompare(norm(b.artist)),
      az: (a, b) => norm(a.name || a.title).localeCompare(norm(b.name || b.title)) };
    view.sort((a, b) => (st(b) - st(a)) || (by[srt] || by.t)(a, b) || norm(a.name).localeCompare(norm(b.name)));
    const own = D.songs.filter(s => st(s) === 2).length, ind = D.songs.filter(s => st(s) === 1).length;
    $('ns').textContent = own + ' mit Herz' + (ind ? ' · ' + ind + ' mit halbem Herz' : '');
    if (!keep || !shown) shown = STEP;
    if (!keep) $('slst').scrollTop = 0;
    $('songs').className = view.length ? '' : 'empty';
    $('songs').innerHTML = songRows(0, shown) || (q.length ? 'Nichts gefunden.' : 'Noch keine Lieder mit Herz. In der Musik-DB, bei Alben und Interpreten das leere Herz antippen.');
    $('more').hidden = shown >= view.length;
    $('badj').disabled = !view.some(s => !s.gone);      // ausgegraut statt versteckt
    drawPlay();
    drawSide(hit, own);
  }

  function songRows(from, to) {
    const st = s => SM.favOf('song', s.path);
    return view.slice(from, to).map((s, k) => {
      const i = from + k;
      const f = st(s);
      return '<div class="song' + (f === 1 ? ' half' : '') + (s.gone ? ' gone' : '') + '">' + SM.favHtml('song', s.path, { name: s.name, artist: s.artist }) +
        '<button class="pb" data-play="' + esc(s.path) + '" data-name="' + esc((s.artist || '') + ' - ' + (s.name || s.title || '')) + '"' + (s.gone ? ' disabled' : '') + '>▶</button>' +
        '<button class="pb nx" data-nx="' + i + '" title="Als Nächstes spielen (kommt im Auto-DJ als nächstes Lied in die Playlist)" aria-label="Als Nächstes spielen"' + (s.gone ? ' disabled' : '') +
        '><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M6.3 4.9v6.2L11.2 8z" fill="currentColor"/></svg></button>' +
        '<img class="cvimg" data-tag="' + i + '" loading="lazy" alt="" title="Antippen: Tag bearbeiten" src="/api/sm/cover?p=' + encodeURIComponent(s.path) + '" onerror="this.style.visibility=&quot;hidden&quot;">' +
        '<div><div class="t">' + esc(s.name || s.title || '') + (s.gone ? ' <span class="dim">(gerade nicht in der Bibliothek)</span>' : '') + '</div><div class="s">' +
        (s.artist ? '<a class="lnk" href="/musik/interpreten?n=' + encodeURIComponent(s.artist) + '">' + esc(s.artist) + '</a>' : '') +
        (s.album ? ' · <a class="lnk" href="/musik/alben?p=' + encodeURIComponent(s.path) + '">' + esc(s.album) + '</a>' : '') +
        esc([s.year || '', s.genre, s.bpm ? Math.round(s.bpm) + ' BPM' : ''].filter(Boolean).map(x => ' · ' + x).join('')) + '</div></div>' +
        '<span class="p">' + (s.plays ? s.plays + '×' : '') + '</span></div>';
    }).join('');
  }
  function moreSongs() {
    if (shown >= view.length) return;
    const from = shown;
    shown = Math.min(view.length, shown + STEP);
    $('songs').insertAdjacentHTML('beforeend', songRows(from, shown));
    $('more').hidden = shown >= view.length;
    drawPlay();
  }

  function drawSide(hit, own) {
    // Alben und Interpreten: nur mit vollem Herz (ein Tipp nimmt sie gleich heraus)
    const al = D.albums.filter(a => SM.favOf('album', a.k) === 2 && hit(words(a.name, a.artist)));
    $('na').textContent = String(al.length);
    $('albums').innerHTML = al.sort((a, b) => (b.ft || 0) - (a.ft || 0)).map(a => '<a class="tile' + (a.gone ? ' gone' : '') + '" href="/musik/alben#k=' + encodeURIComponent(a.k) + '" title="' + esc(a.name) + '">' +
      '<div class="im">' + (a.cover ? '<img loading="lazy" alt="" src="/api/sm/cover?p=' + encodeURIComponent(a.cover) + '" onerror="this.style.visibility=&quot;hidden&quot;">' : '') +
      SM.favHtml('album', a.k, { name: a.name, artist: a.artist, cls: 'oncover' }) + '</div><div class="nm">' + esc(a.name) + '</div><div class="ct">' +
      esc(a.sampler ? 'Verschiedene' : a.artist || '') + (a.year ? ' · ' + a.year : '') + (a.gone ? ' · nicht in der Bibliothek' : '') + '</div></a>').join('') ||
      '<div class="empty">Noch keine Alben mit Herz.</div>';
    const ar = D.artists.filter(a => SM.favOf('artist', a.k) === 2 && hit(words(a.name)));
    $('nr').textContent = String(ar.length);
    $('artists').innerHTML = ar.sort((a, b) => (b.ft || 0) - (a.ft || 0)).map(a => {
      const [bg, fg] = color(a.k);
      return '<a class="tile' + (a.gone ? ' gone' : '') + '" href="/musik/interpreten#k=' + encodeURIComponent(a.k) + '" title="' + esc(a.name) + '">' +
        '<div class="im"' + (a.img ? '' : ' style="background:' + bg + ';color:' + fg + '"') + '>' + (a.img ? '<img loading="lazy" alt="" src="/api/sm/artist_img?k=' + encodeURIComponent(a.k) + '&v=' + a.img + '">' : esc(initials(a.name))) +
        SM.favHtml('artist', a.k, { name: a.name, cls: 'oncover' }) + '</div><div class="nm">' + esc(a.name) + '</div><div class="ct">' + (a.n || 0) + ' Lied' + (a.n === 1 ? '' : 'er') + '</div></a>';
    }).join('') || '<div class="empty">Noch keine Interpreten mit Herz.</div>';
    const ge = D.genres.filter(g => SM.favOf('genre', g.name) === 2 && hit(norm(g.name)));
    $('ng').textContent = String(ge.length);
    $('genres').innerHTML = ge.sort((a, b) => a.name.localeCompare(b.name, 'de', { sensitivity: 'base' })).map(g => '<span class="gchip">' + SM.favHtml('genre', g.name, { cls: 'sm' }) +
      '<a class="lnk" href="/musik/genres">' + esc(g.name) + '</a><span class="n">' + g.n + '</span></span>').join('') || '<span class="n">noch keine · mit „+ Genre“ oder im Genre-Editor</span>';
    $('gadd').innerHTML = '<option value="">+ Genre …</option>' + (D.all_genres || []).filter(([g]) => !SM.favOf('genre', g)).map(([g, n]) => '<option value="' + esc(g) + '">' + esc(g) + ' (' + n + ')</option>').join('');
    $('half').classList.toggle('on', half);
    $('mp3all').disabled = !conf.mp3 || !own;
    $('mp3all').title = conf.mp3 ? 'Schreibt jedem Lied mit eigenem Herz die Bewertung 5 Sterne in die MP3 (Musik-Rechner)' : 'Erst einschalten: Einstellungen allgemein → Panel → „Favoriten auch in die MP3 schreiben“';
  }

  // ---- Vorhoeren ----
  function drawPlay() {
    document.querySelectorAll('#songs button[data-play]').forEach(b => { const on = b.dataset.play === playing && !audio.paused; b.classList.toggle('on', on); b.textContent = on ? '❚❚' : '▶'; });
  }
  async function play(p, name) {
    if (!music) { try { music = (await SM.get('/api/musik/mac')).music || ''; } catch (e) { music = ''; } }
    if (!music) { SM.toast('Der Musik-Rechner ist nicht erreichbar (läuft der Helfer?).', 5000); return; }
    if (playing === p && !audio.paused) { audio.pause(); drawPlay(); return; }
    if (playing !== p) { audio.src = music + '/audio?p=' + encodeURIComponent(p); playing = p; }
    try { await audio.play(); bar.show(name); } catch (e) { SM.toast('Abspielen: ' + e.message, 5000); }
    drawPlay();
  }
  audio.addEventListener('pause', drawPlay);
  audio.addEventListener('play', drawPlay);

  // ---- alle Herzen in die MP3s (Einstellung fav_mp3) ----
  let mp3Busy = false;
  $('mp3all').onclick = async () => {
    if (mp3Busy) { mp3Busy = false; return; }
    const list = D.songs.filter(s => !s.gone && SM.favOf('song', s.path) === 2 && /\.mp3$/i.test(s.path));
    if (!list.length || !await SM.ask(list.length + ' Lieder bekommen in der MP3 die Bewertung 5 Sterne. Die Dateien ändern sich dabei (beim nächsten Spiegeln werden sie neu kopiert). Weiter?')) return;
    mp3Busy = true;
    const b = $('mp3all');
    let ok = 0, bad = 0;
    for (const s of list) {
      if (!mp3Busy) break;
      b.textContent = 'Schreibe ' + (ok + bad + 1) + ' von ' + list.length + ' … (antippen = anhalten)';
      try { await SM.favMp3(s.path, true); ok++; } catch (e) { bad++; $('msg').textContent = 'Nicht gegangen: ' + s.path.split('/').pop() + ': ' + e.message; }
    }
    mp3Busy = false;
    b.textContent = 'Herzen in die MP3s schreiben';
    SM.toast(ok + ' MP3s mit 5 Sternen' + (bad ? ', ' + bad + ' gingen nicht' : '') + '.', 5000);
  };

  // ---- Bedienung ----
  $('badj').onclick = () => SM.autodjAdd(view.filter(s => !s.gone), false, 'Favoriten');   // alle gezeigten hinten an (14.11.2026)
  $('songs').addEventListener('click', e => {
    const n = e.target.closest('button[data-nx]');
    if (n) { const s = view[+n.dataset.nx]; if (s && !s.gone) SM.autodjAdd([s], true); return; }
    const b = e.target.closest('button[data-play]');
    if (b) { play(b.dataset.play, b.dataset.name); return; }
    const im = e.target.closest('img[data-tag]');
    if (im) { const s = view[+im.dataset.tag]; if (s && !s.gone) SM.tagEdit({ path: s.path }, music, () => load()); }
  });
  $('more').onclick = moreSongs;
  $('slst').addEventListener('scroll', () => { const l = $('slst'); if (l.scrollTop + l.clientHeight > l.scrollHeight - 400) moreSongs(); });
  $('q').addEventListener('input', () => { clearTimeout($('q')._t); $('q')._t = setTimeout(() => draw(), 200); });
  $('ssort').onchange = () => draw();
  $('half').onclick = () => { half = !half; try { localStorage.setItem('fav_half', half ? '1' : '0'); } catch (e) { /* egal */ } draw(); };
  $('gadd').onchange = () => { const g = $('gadd').value; if (g) SM.favToggle('genre', g, { name: g }); };
  // Herz anderswo getippt: neue Dinge brauchen die Liste vom Pi, weggenommene verschwinden sofort
  let reload = null;
  document.addEventListener('s2lfav', e => { draw(true); if (e.detail && e.detail.why === 'set') { clearTimeout(reload); reload = setTimeout(load, 600); } });
  load();
})();
