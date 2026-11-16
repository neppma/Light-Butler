// autotag.js - Seite /musik/vorschlaege: Vorschlaege des Auto-Taggers (Wunsch von Markus, 07.11.2026).
// Der Auto-Tagger laeuft am Mac (auto_tag.py in der Mixxx-Bruecke) und recherchiert Lieder ohne Cover vorab. Hier
// erscheinen seine Vorschlaege zum Abhaken; geschrieben wird nur mit "Markierte uebernehmen" (Tags und Cover in die MP3),
// "Ablehnen" merkt sich das Lied, "Ansehen" oeffnet das Fenster Tag bearbeiten mit dem Vorschlag schon eingetragen.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const LABEL = { title: 'Titel', artist: 'Interpret', album: 'Album', albumartist: 'Album-Interpret', year: 'Jahr', track: 'Track', genre: 'Genre' };
  const LEVEL = { gut: 'gut', unsicher: 'unsicher', nichts: 'nichts gefunden', cover: 'nur Cover' };
  const SRC = { tags: 'Tags passen', shazam: 'Shazam', ordner: 'Samples', datei: 'Dateiname passt' };
  let music = '', items = [], status = null, lv = '', busy = false, first = true, playing = '', page = 0;
  const PAGE = 20;                                       // Seiten zu 20 wie bei den Doppelten (Wunsch 07.11.2026: "Riesenwurst")
  const isOn = it => checked.has(it.path) ? checked.get(it.path) : (it.level === 'gut' && (Object.keys(it.new || {}).length || it.cover));
  const canApply = it => it.level !== 'nichts' && it.level !== 'cover';
  const audio = new Audio();
  audio.onended = () => { playing = ''; draw(); };      // nur am Ende: Pause beim Wechsel des Liedes darf den neuen Stand nicht loeschen
  // Lautstaerke oben und Leiste unten zum Spulen (Wunsch 08.11.2026); Lautstaerke gemeinsam mit der Musik-Datenbank
  let vol = 80, seeking = false;
  try { vol = Math.max(0, Math.min(100, parseInt(localStorage.getItem('musikvol') || '80', 10) || 0)); } catch (e) { /* privates Fenster */ }
  const volIcon = v => v == 0 ? '🔇' : v < 50 ? '🔉' : '🔊';
  $('vol').value = vol; audio.volume = vol / 100; $('volbox').firstChild.textContent = volIcon(vol);
  $('vol').addEventListener('input', () => {
    audio.volume = $('vol').value / 100;
    $('volbox').firstChild.textContent = volIcon($('vol').value);
    try { localStorage.setItem('musikvol', $('vol').value); } catch (e) { /* privates Fenster */ }
  });
  const tmss = t => { t = Math.max(0, Math.round(t || 0)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); };
  function drawBar() {
    const on = !!audio.src && (playing || !audio.paused || audio.currentTime > 0) && barOn;
    $('pbar').classList.toggle('on', on); document.body.classList.toggle('bar', on);
    $('ppp').textContent = audio.paused ? '▶' : '❚❚';
    const d = audio.duration || 0;
    if (!seeking) $('ppos').value = d ? Math.round(1000 * audio.currentTime / d) : 0;
    $('ptm').textContent = tmss(audio.currentTime) + ' / ' + tmss(d);
  }
  let barOn = false;
  audio.addEventListener('timeupdate', drawBar);
  audio.addEventListener('play', drawBar); audio.addEventListener('pause', drawBar); audio.addEventListener('loadedmetadata', drawBar);
  $('ppos').addEventListener('input', () => { seeking = true; const d = audio.duration || 0; $('ptm').textContent = tmss(d * $('ppos').value / 1000) + ' / ' + tmss(d); });
  $('ppos').addEventListener('change', () => { const d = audio.duration || 0; if (d) audio.currentTime = d * $('ppos').value / 1000; seeking = false; });
  $('ppp').onclick = () => {
    if (audio.paused) { audio.play().catch(() => {}); playing = barPath; } else { audio.pause(); playing = ''; }
    draw();
  };
  $('pcl').onclick = () => { audio.pause(); playing = ''; barOn = false; draw(); drawBar(); };
  let barPath = '';
  const checked = new Map();
  const gen = new Map(), making = new Set(), saving = new Set();                  // Pfad -> erzeugtes Cover (DataURL); gerade in Arbeit (bleibt beim Neuladen)                                  // Pfad -> angehakt (bleibt beim Neuladen der Liste)

  function line(o, keys) { return keys.filter(k => o[k]).map(k => esc(o[k])).join(' · '); }
  function short(p) { return String(p || '').split('/').pop(); }
  const mmss = d => { d = Math.round(d || 0); return d ? Math.floor(d / 60) + ':' + String(d % 60).padStart(2, '0') : ''; };
  function nowCover(it) { return gen.get(it.path) ? '<div class="acv"><img class="cvimg" src="' + gen.get(it.path) + '" alt="erzeugtes Cover"></div>' : '<div class="acv none" title="kein Cover">–</div>'; }
  function dirOf(p) { const a = String(p || '').split('/'); a.pop(); return a.join('/'); }   // ganzer Ordner (Wunsch 07.11.2026)

  function row(it) {
    const now = it.now || {}, nw = it.new || {}, i = items.indexOf(it);
    const on = checked.has(it.path) ? checked.get(it.path) : (it.level === 'gut' && (Object.keys(nw).length || it.cover));
    const merged = Object.assign({}, now, nw);
    const mark = k => nw[k] ? '<span class="chg" title="' + esc(LABEL[k]) + ' neu">' + esc(nw[k]) + '</span>' : esc(merged[k] || '');
    const head = (merged.artist ? mark('artist') + ' – ' : '') + (mark('title') || esc(short(it.path)));
    const rest = ['album', 'year', 'track', 'genre'].filter(k => merged[k]).map(mark).join(' · ');
    // links der heutige Stand (ohne Cover), rechts der Vorschlag mit seinem Cover (Wunsch von Markus 07.11.2026: das neue Cover
    // links sah aus, als haette das Lied schon eines)
    return '<div class="arow" data-i="' + i + '">' +
      '<input type="checkbox" class="ack"' + (on ? ' checked' : '') + (it.level === 'nichts' || it.level === 'cover' ? ' disabled' : '') + ' aria-label="übernehmen">' +
      '<button class="pb aplay' + (playing === it.path ? ' on' : '') + '" title="Ins Lied hineinhören (die Datei kommt vom Musik-Rechner)">' + (playing === it.path ? '❚❚' : '▶') + '</button>' +
      '<div class="anow"><div class="alab">jetzt <span class="adur">' + mmss(it.dur) + '</span></div><div class="aside">' + nowCover(it) + '<div>' +
      (line(now, ['artist', 'title']) || esc(short(it.path))) + '<div class="alab">' + (line(now, ['album', 'year', 'genre']) || 'ohne Album') + ' · ' +
      (gen.get(it.path) ? '<span class="chg">erzeugtes Cover</span>' : 'kein Cover') + '</div>' +
      (gen.get(it.path) ? '<div class="agen"><button class="agsave on">Cover speichern</button><button class="agdrop">Verwerfen</button></div>' :
        '<div class="agen"><button class="agmake" title="Eigenes Cover nur aus den Angaben, die schon in der Datei stehen (Titel, Interpret, BPM, Tonart, Energie) und der Wellenform. Die Tags bleiben, wie sie sind.">' + (making.has(it.path) ? 'Erzeuge …' : 'Cover erzeugen') + '</button><button class="agedit" title="Tag-Editor mit den Angaben, die jetzt in der Datei stehen (ohne die Vorschläge)">Tag-Editor</button></div>') +
      '</div></div></div>' +
      '<div class="anew"><div class="alab">Vorschlag <span class="lv ' + esc(it.level) + '">' + esc(LEVEL[it.level] || it.level) + '</span>' +
      (it.source ? ' <span class="alab">' + esc(SRC[it.source] || it.source) + '</span>' : '') + '</div><div class="aside">' +
      (it.cover ? '<div class="acv"><img class="cvimg" src="' + esc(it.cover) + '" alt="neues Cover" loading="lazy"></div>' : '<div class="acv none" title="kein Cover gefunden">?</div>') + '<div>' +
      (it.level === 'cover' ? '<span class="alab">Samples: keine Suche im Internet. Links mit „Cover erzeugen“ ein eigenes Cover machen?</span>' :
       it.level === 'nichts' ? '<span class="alab">' + esc(it.error || 'Nichts Passendes gefunden. „Ansehen“ öffnet das Tag-Fenster.') + '</span>' :
        head + '<div>' + (rest || '<span class="alab">keine weiteren Angaben</span>') + (it.cover ? ' · <span class="chg">neues Cover</span>' : '') + '</div>') + '</div></div></div>' +
      '<div class="abtns">' + (canApply(it) ? '<button class="aone" title="Nur diesen Vorschlag in die MP3 schreiben (Tags und Cover)">Übernehmen</button>' : '') +
      '<button class="aview">Ansehen</button>' + (it.rej ? '<button class="aunrej" title="Den Vorschlag wieder unter den offenen zeigen">Wieder anbieten</button>' : '<button class="arej">Ablehnen</button>') +
      '<button class="adel" title="Datei in den Papierkorb des Musik-Rechners legen (mit Rückfrage, wiederherstellbar), zum Beispiel wenn sie kaputt ist">🗑 Löschen</button></div>' +
      '<div class="afile" title="' + esc(it.path) + '">' + esc(short(it.path)) + ' <span>· ' + esc(dirOf(it.path)) + '</span></div></div>';
  }

  function pageItems() {
    const view = items.filter(it => lv === 'rej' ? it.rej : !it.rej && (!lv || (lv === 'ti' ? it.why === 'ti' : it.level === lv)));
    const pages = Math.max(1, Math.ceil(view.length / PAGE));
    page = Math.min(page, pages - 1);
    return { view, pages, cur: view.slice(page * PAGE, page * PAGE + PAGE) };
  }
  function pager(n, pages) {
    if (pages <= 1) return '';
    return '<div class="pager"><button class="pgprev"' + (page ? '' : ' disabled') + '>‹ Zurück</button><span>Seite <b>' + (page + 1) + '</b> von ' + pages +
      ' · Vorschläge ' + (page * PAGE + 1) + '–' + Math.min(n, page * PAGE + PAGE) + ' von ' + n + '</span><button class="pgnext"' + (page < pages - 1 ? '' : ' disabled') + '>Weiter ›</button></div>';
  }
  function draw() {
    if ($('bauto')) drawAuto();
    const { view, pages, cur } = pageItems();
    const pg = pager(view.length, pages);
    if (playing && !cur.some(it => it.path === playing)) { audio.pause(); playing = ''; }   // Zeile weg (uebernommen, andere
    // Seite): Ton aus, sonst gaebe es keinen Knopf mehr dafuer (Fehlerbericht 07.11.2026)
    $('list').innerHTML = view.length ? pg + cur.map(row).join('') + pg :
      '<div class="empty">' + (status && status.running ? 'Noch keine Vorschläge, der Auto-Tagger sucht gerade.' : 'Keine Vorschläge. „Starten“ lässt den Auto-Tagger die Lieder ohne Cover durchgehen.') + '</div>';
    if (busy) return;
    const n = cur.filter(it => canApply(it) && isOn(it)).length;
    $('bapply').textContent = 'Markierte dieser Seite übernehmen (' + n + ')';
  }

  function drawStatus() {
    const s = status;
    if (!s) { $('astat').textContent = music ? 'Der Auto-Tagger läuft in dieser Mixxx-Brücke nicht.' : 'Die Mixxx-Brücke am Musik-Rechner ist nicht verbunden.'; $('bgo').disabled = true; return; }
    $('bgo').disabled = false;
    $('bgo').textContent = s.on ? 'Anhalten' : 'Starten';
    $('bgo').classList.toggle('on', !!s.on);
    // Anzahl je Reiter in den Knoepfen (Wunsch 07.11.2026), oben nur noch erledigt und abgelehnt
    const cnt = { '': s.open, gut: s.good, unsicher: s.unsure, nichts: s.none, cover: s.cover, ti: s.ti || 0, rej: items.filter(x => x.rej).length };
    const LAB = { '': 'Alle', gut: 'gut', unsicher: 'unsicher', nichts: 'nichts gefunden', cover: 'nur Cover', ti: 'Titel = Interpret' + (s.ti_queue ? ', ' + s.ti_queue + ' in Arbeit' : ''), rej: 'Abgelehnt' };
    document.querySelectorAll('#lvtabs button[data-lv]').forEach(b => { b.textContent = LAB[b.dataset.lv] + ' (' + (cnt[b.dataset.lv] || 0) + ')'; });
    const ba = $('bauto2');
    if (ba) {
      ba.textContent = 'Gute automatisch übernehmen: ' + (s.auto ? 'an' : 'aus') + (s.auto && s.auto_n ? ' (' + s.auto_n + ' übernommen)' : '');
      ba.classList.toggle('on', !!s.auto);
    }
    $('astat').innerHTML = 'erledigt ' + s.done + ' · abgelehnt ' + s.rejected +
      (s.running && s.current ? ' · <b>sucht:</b> ' + esc(s.current) : s.on ? ' · wartet auf neue Lieder ohne Cover' : ' · angehalten') + (s.shazam ? '' : ' · ohne Shazam (ffmpeg fehlt am Musik-Rechner)');
    $('aerr').textContent = (s.error ? 'Zuletzt: ' + s.error + ' (versucht es später wieder)' : '') + (s.auto && s.auto_err ? ' Automatisch übernehmen ging nicht bei ' + s.auto_err + ' (nächster Versuch in ein paar Minuten).' : '');
  }

  // ---- Ordnerbilder in MP3s ohne eigenes Bild (Wunsch 08.11.2026): suchen und schreiben am Mac, nie ueberschreiben ----
  let fartT = null;
  async function fart(op, body) {
    if (!music) throw new Error('Der Light-Butler erreicht den Musik-Rechner gerade nicht');
    const r = await fetch(music + '/folderart', op ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ op }, body || {})) } : {});
    let d = null;
    try { d = JSON.parse(await r.text()); } catch (e) { d = null; }   // alte Bruecke antwortet mit Text "nicht gefunden"
    if (r.status === 404 || !d || d.state === 'off') throw new Error('Am Musik-Rechner läuft noch die alte Fassung. Nach dem nächsten Start der Mixxx-App am Musik-Rechner geht es.');
    if (!r.ok) throw new Error(d.error || 'ging nicht (' + r.status + ')');
    return d;
  }
  function drawFart(d) {
    const busyF = d.state === 'scan' || d.state === 'write';
    $('fscan').disabled = busyF;
    $('fscan').textContent = d.state === 'idle' ? 'Suchen' : 'Neu suchen';
    $('fwrite').hidden = d.state !== 'ready' || !d.n;
    $('fwrite').textContent = 'Alle ' + d.n + ' übernehmen';
    $('fst').textContent = d.state === 'scan' ? 'Suche … ' + d.done + ' von ' + d.total + ' MP3s'
      : d.state === 'write' ? 'Schreibe … ' + d.done + ' von ' + d.total
      : d.state === 'ready' ? (d.n ? d.n + ' MP3s ohne eigenes Bild, im Ordner liegt eins.' : 'Keine MP3 gefunden, der ein Bild fehlt, das im Ordner liegt.')
        + (d.written ? ' Zuletzt geschrieben: ' + d.written + '.' : '') + (d.errors && d.errors.length ? ' Fehler: ' + d.errors.length : '') : '';
    $('flist').innerHTML = (d.items || []).map(x => '<div>' + esc(short(x.path)) + ' <span style="color:#9fd0ff">← ' + esc(x.image) + '</span></div>').join('')
      + (d.n > (d.items || []).length ? '<div>… und ' + (d.n - d.items.length) + ' weitere</div>' : '')
      + (d.errors || []).map(e => '<div style="color:#ff8a80">' + esc(e) + '</div>').join('');
    clearTimeout(fartT);
    if (busyF) fartT = setTimeout(pollFart, 1500);
  }
  async function pollFart() { try { drawFart(await fart()); } catch (e) { $('fst').textContent = e.message; } }
  $('fart').addEventListener('toggle', () => { if ($('fart').open) pollFart(); });
  $('fscan').onclick = async () => { try { drawFart(await fart('scan')); } catch (e) { $('fst').textContent = e.message; } };
  $('fwrite').onclick = async () => {
    let d;
    try { d = await fart(); } catch (e) { $('fst').textContent = e.message; return; }
    if (!await SM.ask(d.n + ' MP3s bekommen das Bild aus ihrem Ordner.\n\nNur Dateien ohne eigenes Bild, ein vorhandenes wird nie überschrieben. Die Musik bleibt unverändert.', undefined, 'Übernehmen')) return;
    try { drawFart(await fart('write')); } catch (e) { $('fst').textContent = e.message; }
  };

  async function load() {
    try {
      if (!music) music = ((await fetch('/api/musik/mac').then(r => r.json())) || {}).music || '';
      if (!music) { status = null; drawStatus(); $('list').innerHTML = '<div class="empty">Der Light-Butler erreicht den Musik-Rechner gerade nicht. Läuft dort die Mixxx-App oder der Light-Butler Helfer? Nach einem Neustart dauert es bis zu einer Minute.</div>'; return; }
      if (fartFirst) { fartFirst = false; $('fart').open = true; }
      const d = await fetch(music + '/autotag').then(r => r.json());
      status = d.status;
      const before = items.map(x => x.path).join('|');
      const ord = { gut: 0, unsicher: 1, nichts: 2, cover: 3 };
      items = (d.items || []).sort((a, b) => (ord[a.level] - ord[b.level]) || (a.t || 0) - (b.t || 0));
      drawStatus();
      if (!busy && !saving.size && (first || items.map(x => x.path).join('|') !== before)) draw();
      first = false;
    } catch (e) {
      $('aerr').textContent = 'Keine Verbindung zum Musik-Rechner: ' + e.message;
    }
  }

  // erzeugtes Cover in die MP3 (nur das Bild, die Tags bleiben), Vorschlag erledigt, Pi holt das Bild im Hintergrund
  async function saveCover(it) {
    saving.add(it.path);
    try {
      const resp = await fetch(music + '/tags', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ p: it.path, name: short(it.path), fields: {}, cover_data: gen.get(it.path).split(',')[1] }) });
      const d = await resp.json().catch(() => ({}));
      if (!resp.ok || !d.ok) throw new Error(d.error || ('Fehler ' + resp.status));
      try { await post({ op: 'done', path: it.path }); } catch (err) { /* faellt beim naechsten Aufraeumen heraus */ }
      SM.cmd('cover_refresh', { path: it.path }).catch(() => {});
      gen.delete(it.path);
    } finally {
      saving.delete(it.path);
    }
  }

  // Automatik fuer "nur Cover" (Wunsch 07.11.2026): ein Lied nach dem anderen, Cover erzeugen und speichern; Anhalten jederzeit
  let autoRun = false;
  // fuer welche Lieder: im Reiter "nichts gefunden" diese (Wunsch 07.11.2026), sonst "nur Cover" (Samples)
  const autoLevel = () => (lv === 'nichts' ? 'nichts' : lv === 'rej' ? 'rej' : 'cover');
  async function autoCovers() {
    if (autoRun) { autoRun = false; return; }
    const level = autoLevel();
    const todo = items.filter(it => level === 'rej' ? it.rej : !it.rej && it.level === level);
    if (!todo.length) return;
    if (!await SM.ask(todo.length + (level === 'nichts' ? ' Lieder, zu denen nichts gefunden wurde' : level === 'rej' ? ' abgelehnte Lieder' : ' Lieder ohne Suche (Samples)') + ': für jedes ein Cover erzeugen und gleich in die MP3 speichern?\n\nNur das Bild kommt in die Datei, die Tags bleiben, wie sie sind. Anhalten geht jederzeit.', undefined, 'Starten')) return;
    autoRun = true; busy = true;
    let ok = 0, n = 0;
    const errs = [];
    for (const it of todo) {
      if (!autoRun) break;
      n++;
      $('bauto').textContent = 'Anhalten (' + n + ' von ' + todo.length + ')';
      making.add(it.path); draw();
      try {
        gen.set(it.path, await SM.coverFor(music, it.path));
        making.delete(it.path); draw();
        await saveCover(it);
        ok++;
        items = items.filter(x => x.path !== it.path);
      } catch (err) {
        making.delete(it.path); gen.delete(it.path);
        errs.push(short(it.path) + ': ' + err.message);
      }
      draw();
    }
    autoRun = false; busy = false;
    drawAuto(); draw();
    SM.toast(ok + ' Cover erzeugt und gespeichert' + (errs.length ? ', ' + errs.length + ' nicht gegangen' : '') + '.', 6000);
    if (errs.length) $('aerr').textContent = 'Nicht gegangen: ' + errs.slice(0, 3).join('; ');
  }
  function drawAuto() {
    const n = items.filter(it => autoLevel() === 'rej' ? it.rej : !it.rej && it.level === autoLevel()).length;
    $('bauto').hidden = (!n || (lv !== 'cover' && lv !== 'nichts' && lv !== 'rej' && autoLevel() !== 'cover')) && !autoRun;
    if (!autoRun) $('bauto').textContent = (lv === 'nichts' || lv === 'rej' ? 'Für alle Cover erzeugen' : 'Alle Cover automatisch') + ' (' + n + ')';
    $('bauto').classList.toggle('on', autoRun);
  }

  async function post(body) {
    const r = await fetch(music + '/autotag', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || d.error) throw new Error(d.error || ('Fehler ' + r.status));
    if (d.status) { status = d.status; drawStatus(); }
    return d;
  }

  $('bauto').onclick = autoCovers;
  $('bauto2').onclick = async () => {
    const on = !(status && status.auto);
    if (on && !await SM.ask('Alle Vorschläge „gut“ (' + ((status && status.good) || 0) + ') gleich in die MP3s schreiben, Tags und Cover, und ab jetzt jeden neuen guten sofort?\n\nDas läuft am Musik-Rechner, auch wenn diese Seite zu ist. Die unsicheren bleiben für dich. Ausschalten geht jederzeit.', undefined, 'Einschalten')) return;
    try { await post({ op: 'auto', on }); SM.toast(on ? 'Gute werden automatisch übernommen.' : 'Automatisch übernehmen ist aus.', 4000); } catch (e) { $('aerr').textContent = e.message; }
  };
  $('bgo').onclick = async () => { try { await post({ op: status && status.on ? 'stop' : 'start' }); } catch (e) { $('aerr').textContent = e.message; } };
  $('lvtabs').addEventListener('click', e => {
    const b = e.target.closest('button[data-lv]');
    if (!b) return;
    lv = b.dataset.lv; page = 0;
    document.querySelectorAll('#lvtabs button').forEach(x => x.classList.toggle('on', x === b));
    draw();
  });
  $('ball').onchange = e => { pageItems().cur.filter(canApply).forEach(it => checked.set(it.path, e.target.checked)); draw(); };
  $('list').addEventListener('change', e => {
    const r = e.target.closest('.arow');
    if (r && e.target.classList.contains('ack')) { checked.set(items[+r.dataset.i].path, e.target.checked); draw(); }
  });
  $('list').addEventListener('click', async e => {
    if (e.target.closest('.pgprev')) { page--; $('ball').checked = false; draw(); window.scrollTo(0, 0); return; }
    if (e.target.closest('.pgnext')) { page++; $('ball').checked = false; draw(); window.scrollTo(0, 0); return; }
    const r = e.target.closest('.arow');
    if (!r) return;
    const it = items[+r.dataset.i];
    if (e.target.classList.contains('adel')) {                // Datei loeschen, ohne Umweg ueber die Musik-Datenbank (Wunsch 07.11.2026)
      if (busy) return;
      SM.toast('In den Papierkorb: ' + it.path.split('/').pop() + ' (im Finder mit „Zurücklegen“ wieder da)', 3500);   // ohne Nachfrage (Wunsch 08.11.2026)
      if (playing === it.path) { audio.pause(); playing = ''; }
      try {
        const r = await fetch(music + '/trash', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ p: it.path, name: short(it.path) }) });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.ok) throw new Error(j.error || ('Fehler ' + r.status));
        SM.goneMark(it.path);                                    // auch die Musik-Datenbank zeigt sie nicht mehr
        try { await post({ op: 'reject', path: it.path }); } catch (err) { /* faellt ohnehin heraus: Datei fehlt */ }
        items = items.filter(x => x !== it); draw();
        SM.toast('In den Papierkorb gelegt: ' + short(it.path), 4000);
      } catch (err) {
        $('aerr').textContent = 'Löschen ging nicht (' + short(it.path) + '): ' + err.message + (/Finder|Apple/i.test(err.message) ? ' – beim ersten Mal fragt macOS am Mac, ob die App den Finder steuern darf: dort erlauben.' : '');
      }
      return;
    }
    if (e.target.classList.contains('aone')) {                // nur dieser eine Vorschlag (Wunsch 07.11.2026)
      if (busy) return;
      e.target.disabled = true; e.target.textContent = 'Schreibe …';
      await applyItems([it]);
      return;
    }
    if (e.target.classList.contains('agmake')) {             // Cover erzeugen links: nur aus den Tags der Datei, Tags bleiben
      if (making.has(it.path)) return;
      making.add(it.path); draw();
      try { gen.set(it.path, await SM.coverFor(music, it.path)); } catch (err) { $('aerr').textContent = 'Cover erzeugen ging nicht: ' + err.message; }
      making.delete(it.path); draw();
      return;
    }
    if (e.target.classList.contains('agedit')) {             // Tag-Editor fuer die Datei, wie sie ist (Wunsch 07.11.2026)
      SM.tagEdit({ path: it.path, dur: it.dur || 0 }, music, async d => {
        if (d && d.cover) {                                   // hat jetzt ein Cover: Vorschlag erledigt
          try { await post({ op: 'done', path: it.path }); } catch (err) { /* faellt beim Aufraeumen heraus */ }
          items = items.filter(x => x.path !== it.path); draw();
        }
      });
      return;
    }
    if (e.target.classList.contains('agdrop')) { gen.delete(it.path); draw(); return; }
    if (e.target.classList.contains('agsave')) {
      const b = e.target;
      if (saving.has(it.path)) return;
      b.disabled = true; b.textContent = 'Speichere …';               // Rueckmeldung (Fehlerbericht 07.11.2026: Knopf blieb gleich)
      try {
        await saveCover(it);
        b.textContent = '✓ Gespeichert';
        SM.toast('Cover gespeichert: ' + short(it.path), 4000);
        await new Promise(res => setTimeout(res, 900));
        items = items.filter(x => x.path !== it.path); draw();
      } catch (err) {
        b.disabled = false; b.textContent = 'Cover speichern';
        $('aerr').textContent = 'Speichern ging nicht (' + short(it.path) + '): ' + err.message;
      }
      return;
    }
    if (e.target.closest('.aplay')) {                         // Hineinhoeren: ab einem Drittel, dort laeuft das Lied sicher
      if (playing === it.path) { audio.pause(); playing = ''; draw(); return; }
      if (barPath === it.path && audio.src) { playing = it.path; audio.play().catch(() => {}); draw(); return; }   // weiter, wo es war
      audio.src = music + '/audio?p=' + encodeURIComponent(it.path);
      playing = barPath = it.path; barOn = true;
      $('pt').textContent = short(it.path);
      audio.onloadedmetadata = () => { if (audio.duration > 60) audio.currentTime = audio.duration / 3; };
      audio.play().catch(err => { playing = ''; $('aerr').textContent = 'Abspielen ging nicht: ' + err.message; draw(); });
      draw();
      return;
    }
    if (e.target.classList.contains('arej')) {
      if (playing === it.path) { audio.pause(); playing = ''; }
      try { await post({ op: 'reject', path: it.path }); it.rej = true; drawStatus(); draw(); } catch (err) { $('aerr').textContent = err.message; }   // in den Reiter Abgelehnt
    } else if (e.target.classList.contains('aunrej')) {
      try { await post({ op: 'unreject', path: it.path }); it.rej = false; drawStatus(); draw(); } catch (err) { $('aerr').textContent = err.message; }
    } else if (e.target.classList.contains('aview')) {
      SM.tagEdit({ path: it.path, dur: 0 }, music, async () => {
        try { await post({ op: 'done', path: it.path }); } catch (err) { /* Vorschlag bleibt dann stehen */ }
        items = items.filter(x => x !== it); draw();
      }, { fields: it.new || {}, cover: it.cover || '' });
    }
  });
  $('bapply').onclick = async () => {
    const todo = pageItems().cur.filter(it => canApply(it) && isOn(it));      // nur diese Seite, wie bei den Doppelten
    if (!todo.length || busy) return;
    if (!await SM.ask(todo.length + ' Vorschläge dieser Seite in die MP3s schreiben (Tags und Cover)?\n\nDie Musik bleibt unverändert. Die Liste der Musik-Datenbank zeigt die neuen Angaben gleich, Mixxx erst nach „Metadaten aus Datei importieren“.', undefined, 'Übernehmen')) return;
    await applyItems(todo);
  };
  async function applyItems(todo) {
    busy = true;
    audio.pause();
    playing = '';
    let ok = 0;
    const errs = [];
    for (const it of todo) {
      $('bapply').textContent = 'Schreibe ' + (ok + errs.length + 1) + ' von ' + todo.length + ' …';
      try {
        await post({ op: 'apply', path: it.path });
        ok++;
        items = items.filter(x => x !== it);
        if (it.cover) { try { await SM.cmd('cover_refresh', { path: it.path }); } catch (e) { /* Cover kommt spaeter */ } }
      } catch (e) {
        errs.push(short(it.path) + ': ' + e.message);
      }
    }
    busy = false;
    $('ball').checked = false;
    draw();
    const msg = ok + ' übernommen' + (errs.length ? ', nicht gegangen: ' + errs.slice(0, 3).join('; ') : '') + '.';
    SM.toast(msg, errs.length ? 9000 : 4000);
    if (errs.length) SM.ask(msg);
  }

  let fartFirst = new URLSearchParams(location.search).get('f') === 'ordner';   // aus der Datenpflege: Ordnerbilder aufklappen
  if (new URLSearchParams(location.search).get('f') === 'ti') {   // aus der Musik-DB: gleich den Reiter Titel = Interpret
    lv = 'ti';
    document.querySelectorAll('#lvtabs button').forEach(x => x.classList.toggle('on', x.dataset.lv === 'ti'));
  }
  load();
  setInterval(load, 5000);
})();
