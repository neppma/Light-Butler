// Beschaedigte Dateien (Wunsch von Markus, 14.11.2026, Datenpflege): was macOS (und damit Mixxx am Mac) nicht oeffnen kann.
// Der Musik-Rechner prueft im Hintergrund (damaged.py, music_serve /defekt) und repariert nur auf Klick (ffmpeg ohne Neukodieren).
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = SM.esc;
  let music = '', D = { items: [] }, timer = 0, playing = '';
  const audio = new Audio();
  const bar = SM.playBar(audio, { onclose: () => { audio.pause(); playing = ''; drawPlay(); } });
  const name = p => String(p).split('/').pop();
  const dir = p => String(p).split('/').slice(0, -1).join('/');
  const msg = (t, cls) => { $('msg').className = cls || ''; $('msg').textContent = t || ''; };

  async function load() {
    clearTimeout(timer);
    try {
      if (!music) music = (await SM.get('/api/musik/mac')).music || '';
      if (!music) throw new Error('Musik-Rechner nicht erreichbar (läuft der Helfer?)');
      D = await (await fetch(music + '/defekt')).json();
    } catch (e) { $('list').className = 'empty'; $('list').textContent = e.message; return; }
    draw();
    const busy = D.state === 'busy' || (D.job && D.job.state === 'run');
    timer = setTimeout(load, busy ? 3000 : 30000);
  }

  function draw() {
    const items = D.items || [], j = D.job;
    const pr = D.progress || [0, 0];
    $('st').textContent = D.state === 'off' ? 'Am Musik-Rechner noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren).'
      : (D.state === 'busy' ? 'Prüfe: ' + pr[0] + ' von ' + pr[1] + ' Dateien … ' : D.state === 'wait' ? 'Die Prüfung beginnt gleich … ' : 'Geprüft. ') +
        items.length + (items.length === 1 ? ' beschädigte Datei' : ' beschädigte Dateien') + (D.ffmpeg === false ? ' · ffmpeg fehlt am Musik-Rechner (brew install ffmpeg)' : '');
    if (j && j.state === 'run') msg('Repariere: ' + j.done + ' von ' + j.total + ' …');
    else if (j && j.state === 'done' && !$('msg').dataset.shown) { $('msg').dataset.shown = '1'; msg(j.ok + ' repariert' + (j.done - j.ok ? ', ' + (j.done - j.ok) + ' nicht (' + j.err + ')' : '') + '.', j.done - j.ok ? 'bad' : 'ok'); }
    const fixable = items.filter(x => x.mp3 && !x.fix);
    $('ball').disabled = !fixable.length || !D.ffmpeg || !!(j && j.state === 'run');
    $('ball').textContent = 'Alle MP3s reparieren' + (fixable.length ? ' (' + fixable.length + ')' : '');
    $('list').className = items.length ? '' : 'empty';
    $('list').innerHTML = items.map((x, i) => '<div class="it" data-i="' + i + '">' +
      '<button class="pb" data-play="' + esc(x.path) + '" title="Vorhören (geht nur, wenn der Browser die Datei lesen kann)">▶</button>' +
      '<img class="cvimg" data-tag="' + esc(x.path) + '" loading="lazy" alt="" title="Antippen: Tag bearbeiten" src="/api/sm/cover?p=' + encodeURIComponent(x.path) + '" onerror="this.style.visibility=&quot;hidden&quot;">' +
      '<div><div class="t">' + esc(name(x.path)) + '</div><div class="f">' + esc(dir(x.path)) + '</div><div class="w">' + esc(x.why) + '</div>' +
      (x.fix && x.fix !== 1 ? '<div class="x">Nicht reparierbar: ' + esc(x.fix) + '</div>' : '') + '</div>' +
      '<div class="acts">' + (x.mp3 ? '<button data-fix="' + i + '"' + (D.ffmpeg && !(j && j.state === 'run') ? '' : ' disabled') + '>Reparieren</button>' : '<a class="btn" href="/musik?q=' + encodeURIComponent(name(x.path)) + '" title="In der Musik-Datenbank mit → MP3 umwandeln">→ MP3</a>') +
      '<button data-trash="' + i + '" title="In den Papierkorb des Musik-Rechners (mit Rückfrage)">🗑</button></div></div>').join('') ||
      (D.state === 'ok' ? 'Keine beschädigten Dateien gefunden.' : 'Noch nichts gefunden.');
    drawPlay();
  }
  function drawPlay() {
    document.querySelectorAll('#list button[data-play]').forEach(b => { const on = b.dataset.play === playing && !audio.paused; b.classList.toggle('on', on); b.textContent = on ? '❚❚' : '▶'; });
  }
  audio.addEventListener('pause', drawPlay); audio.addEventListener('play', drawPlay);
  audio.addEventListener('error', () => { if (playing) SM.toast('Auch der Browser kann diese Datei nicht abspielen.', 4000); });

  async function post(body) {
    const r = await fetch(music + '/defekt', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json(); if (!r.ok || d.error) throw new Error(d.error || r.statusText); return d;
  }
  async function repair(paths) {
    if (!paths.length) return;
    if (!await SM.ask(paths.length === 1 ? '„' + name(paths[0]) + '“ reparieren? Das Original kommt in den Papierkorb des Musik-Rechners, wenn die neue Fassung passt.'
      : paths.length + ' MP3s reparieren? Je Datei kommt das Original in den Papierkorb des Musik-Rechners, wenn die neue Fassung passt.', undefined, 'Reparieren')) return;
    delete $('msg').dataset.shown;
    try { await post({ op: 'repair', paths }); msg('Repariere …'); setTimeout(load, 800); }
    catch (e) { msg('Reparieren: ' + e.message, 'bad'); }
  }
  $('ball').onclick = () => repair((D.items || []).filter(x => x.mp3 && !x.fix).map(x => x.path));
  $('list').addEventListener('click', async e => {
    const im = e.target.closest('img[data-tag]');
    if (im) { if (/\.mp3$/i.test(im.dataset.tag)) SM.tagEdit({ path: im.dataset.tag }, music, () => load()); else SM.toast('Tags bearbeiten geht nur bei MP3', 3000); return; }
    const b = e.target.closest('button'); if (!b) return;
    const items = D.items || [];
    if (b.dataset.play) {
      const p = b.dataset.play;
      if (playing === p && !audio.paused) { audio.pause(); return; }
      if (playing !== p) { audio.src = music + '/audio?p=' + encodeURIComponent(p); playing = p; }
      try { await audio.play(); bar.show(name(p)); } catch (err) { /* Fehler zeigt der error-Handler */ }
      return;
    }
    if (b.dataset.fix != null) { repair([items[+b.dataset.fix].path]); return; }
    if (b.dataset.trash != null) {
      const x = items[+b.dataset.trash];
      if (!await SM.ask('„' + name(x.path) + '“ in den Papierkorb des Musik-Rechners legen? Im Finder holt „Zurücklegen“ sie zurück, bis du den Papierkorb leerst. Mixxx zeigt sie, bis es die Bibliothek neu einliest.', undefined, 'In den Papierkorb')) return;
      try { await post({ op: 'trash', path: x.path }); msg('In den Papierkorb gelegt: ' + name(x.path), 'ok'); load(); }
      catch (err) { msg('Papierkorb: ' + err.message, 'bad'); }
    }
  });
  load();
})();
