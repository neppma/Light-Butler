// Lose Album-Lieder (Wunsch von Markus, 14.11.2026): Lieder, die lose im Interpreten-Ordner liegen, in ihren Album-Ordner
// verschieben. Liste und Verschieben macht der Musik-Rechner (music_serve /lose, album_loose.py), nie ueberschreiben, Protokoll.
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const PER = 20;
  let music = '', D = { albums: [], history: [] }, page = 0, busy = false;
  const off = new Set();                                 // abgewaehlte Lieder (Datei)
  const audio = new Audio();
  let playing = '';
  const bar = SM.playBar(audio, { onclose: () => { audio.pause(); playing = ''; drawPlay(); } });

  async function load() {
    $('stat').textContent = 'Der Musik-Rechner sucht …';
    try {
      if (!music) music = (await SM.get('/api/musik/mac')).music || '';
      if (!music) throw new Error('Musik-Rechner nicht erreichbar (läuft der Helfer?)');
      const r = await fetch(music + '/lose');
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || ('Fehler ' + r.status));
      D = d;
    } catch (e) { $('stat').textContent = e.message; $('ball').disabled = true; return; }
    page = Math.max(0, Math.min(page, Math.ceil(D.albums.length / PER) - 1));
    draw();
  }

  function draw() {
    const n = D.albums.length;
    $('stat').textContent = n ? n + ' Alben mit ' + D.songs + ' losen Liedern' : 'Keine losen Album-Lieder: alles liegt in seinem Album-Ordner.';
    const part = D.albums.slice(page * PER, (page + 1) * PER);
    $('list').innerHTML = part.map((a, i) => '<div class="alb" data-a="' + (page * PER + i) + '"><div class="ah"><img class="cvimg" alt="" loading="lazy" src="/api/sm/cover?p=' + encodeURIComponent(a.cover) +
      '" onerror="this.style.visibility=&quot;hidden&quot;"><div style="min-width:0"><div class="t">' + esc(a.artist) + ' – ' + esc(a.album) + '</div><div class="s">kommt nach <b>' + esc(a.rel_target) + '</b> (dort ' + a.n_album + ' Lied' + (a.n_album === 1 ? '' : 'er') + ')</div></div>' +
      '<button data-one="' + (page * PER + i) + '"' + (busy ? ' disabled' : '') + '>Verschieben</button></div>' +
      a.songs.map(s => '<div class="song' + (s.exists ? ' ex' : '') + '"><input type="checkbox" data-f="' + esc(s.file) + '"' + (s.exists ? ' disabled title="Im Album-Ordner gibt es schon eine Datei mit diesem Namen"' : off.has(s.file) ? '' : ' checked') + '>' +
        '<button class="pb" data-play="' + esc(s.path) + '" data-name="' + esc(a.artist + ' - ' + s.title) + '">▶</button>' +
        '<img class="cvimg" alt="" loading="lazy" title="Antippen: Tag bearbeiten" data-tag="' + esc(s.path) + '" src="/api/sm/cover?p=' + encodeURIComponent(s.path) +
        '" onerror="this.style.visibility=&quot;hidden&quot;"><div><div>' + (parseInt(s.track, 10) ? '<span class="no" title="Tracknummer aus dem Tag">' + parseInt(s.track, 10) + '</span>' : '') + esc(s.title || s.rel.split('/').pop()) + '</div><div class="f">' + esc(s.rel) + '</div>' +
        (s.exists ? '<div class="warn">Im Album-Ordner liegt schon eine Datei mit diesem Namen: bleibt liegen</div>' : '') + '</div></div>').join('') + '</div>').join('');
    const pages = Math.ceil(n / PER);
    $('pg1').innerHTML = $('pg2').innerHTML = pages > 1 ? '<button data-pg="' + (page - 1) + '"' + (page ? '' : ' disabled') + '>‹ zurück</button><span>Seite <b>' + (page + 1) + '</b> von ' + pages +
      '</span><button data-pg="' + (page + 1) + '"' + (page < pages - 1 ? '' : ' disabled') + '>weiter ›</button>' : '';
    $('ball').disabled = busy || !part.length;
    const h = D.history || [];
    $('hist').innerHTML = h.length ? h.map(x => '<div class="h"><span>' + new Date(x.t * 1000).toLocaleString('de-AT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + ' · ' + x.n + ' Lied' + (x.n === 1 ? '' : 'er') +
      (x.albums && x.albums.length ? ' · ' + esc(x.albums.slice(0, 3).join(', ')) + (x.albums.length > 3 ? ' …' : '') : '') + '</span>' +
      (x.undone ? '<span class="dim" style="flex:none">zurückgenommen</span>' : '<button data-undo="' + x.t + '"' + (busy ? ' disabled' : '') + '>Zurücknehmen</button>') + '</div>').join('') : '<div class="dim">Noch nichts verschoben.</div>';
    drawPlay();
  }

  function items(albs) {
    const out = [];
    for (const a of albs) for (const s of a.songs) if (!s.exists && !off.has(s.file)) out.push({ path: s.path, file: s.file, target: a.target });
    return out;
  }
  async function post(body) {
    const r = await fetch(music + '/lose', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ('Fehler ' + r.status));
    return d;
  }
  async function move(albs) {
    const it = items(albs);
    if (!it.length || busy) return;
    if (!await SM.ask(it.length + ' Lied' + (it.length === 1 ? '' : 'er') + ' in ' + (albs.length === 1 ? 'den Album-Ordner' : 'ihre Album-Ordner') + ' verschieben?\n\nDer Dateiname bleibt, überschrieben wird nie. Mixxx übernimmt die neuen Pfade beim nächsten Start der Mixxx-App.', undefined, 'Verschieben')) return;
    busy = true; draw();
    try {
      const d = await post({ op: 'apply', items: it });
      $('msg').innerHTML = '<span class="ok">' + d.moved + ' verschoben.</span>' + (d.errors && d.errors.length ? ' <span class="bad">' + esc(d.errors.slice(0, 5).join(' · ')) + '</span>' : '');
    } catch (e) { $('msg').innerHTML = '<span class="bad">Verschieben ging nicht: ' + esc(e.message) + '</span>'; }
    busy = false;
    await load();
  }

  function drawPlay() {
    document.querySelectorAll('#list button[data-play]').forEach(b => { const on = b.dataset.play === playing && !audio.paused; b.classList.toggle('on', on); b.textContent = on ? '❚❚' : '▶'; });
  }
  async function play(p, name) {
    if (!music) return;
    if (playing === p && !audio.paused) { audio.pause(); drawPlay(); return; }
    if (playing !== p) { audio.src = music + '/audio?p=' + encodeURIComponent(p); playing = p; }
    try { await audio.play(); bar.show(name); } catch (e) { SM.toast('Abspielen: ' + e.message, 5000); }
    drawPlay();
  }
  audio.addEventListener('pause', drawPlay);
  audio.addEventListener('play', drawPlay);

  $('list').addEventListener('click', e => {
    const p = e.target.closest('button[data-play]');
    if (p) { play(p.dataset.play, p.dataset.name); return; }
    const im = e.target.closest('img[data-tag]');          // Cover antippen: Tag bearbeiten (Wunsch 14.11.2026)
    if (im) { if (/\.mp3$/i.test(im.dataset.tag)) SM.tagEdit({ path: im.dataset.tag }, music, () => load()); else SM.toast('Tags bearbeiten geht nur bei MP3', 3000); return; }
    const o = e.target.closest('button[data-one]');
    if (o) move([D.albums[+o.dataset.one]]);
  });
  $('list').addEventListener('change', e => {
    const c = e.target.closest('input[data-f]');
    if (c) { if (c.checked) off.delete(c.dataset.f); else off.add(c.dataset.f); }
  });
  for (const id of ['pg1', 'pg2']) $(id).addEventListener('click', e => { const b = e.target.closest('button[data-pg]'); if (b && !b.disabled) { page = +b.dataset.pg; draw(); scrollTo(0, 0); } });
  $('ball').onclick = () => move(D.albums.slice(page * PER, (page + 1) * PER));
  $('breload').onclick = load;
  $('hist').addEventListener('click', async e => {
    const b = e.target.closest('button[data-undo]');
    if (!b || busy || !await SM.ask('Diesen Schritt zurücknehmen? Die Dateien kommen an ihren alten Platz (wo dort nichts liegt).', undefined, 'Zurücknehmen')) return;
    busy = true; draw();
    try {
      const d = await post({ op: 'undo', t: +b.dataset.undo });
      $('msg').innerHTML = '<span class="ok">' + d.back + ' zurückgelegt.</span>' + (d.errors && d.errors.length ? ' <span class="bad">' + esc(d.errors.slice(0, 5).join(' · ')) + '</span>' : '');
    } catch (err) { $('msg').innerHTML = '<span class="bad">Zurücknehmen ging nicht: ' + esc(err.message) + '</span>'; }
    busy = false;
    await load();
  });
  load();
})();
