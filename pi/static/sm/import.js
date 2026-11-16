// Import neuer Musik (Wunsch 10.11.2026): Wartebereich musik-import neben dem Musikordner. Der Mac liest ihn (GET /import),
// schlaegt das Ziel vor und verschiebt auf Knopfdruck (POST /import, mac/mixxx_bridge/import_assist.py). Vorhoeren mit der
// gemeinsamen Leiste unten (SM.playBar), Tags mit dem Fenster "Tag bearbeiten" (SM.tagEdit).
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const mmss = s => s ? Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0') : '';
  const audio = new Audio();
  let music = '', data = null, playing = '', choice = {}, target = {}, top = 'U-MUSIK', busy = false;
  // Reiter je Unterordner, Seiten zu PAGE Liedern (Wunsch 10.11.2026: in Haeppchen abarbeiten, nichts wird gemerkt);
  // "Ausfuehren" und "Fuer alle" gelten nur fuer die gezeigte Seite
  const PAGE = 20;
  let tab = null, page = 0, stamp = Date.now();   // stamp: Cover nach dem Neuladen frisch holen (Tag geaendert)
  const pbar = SM.playBar(audio, { onclose: () => { playing = ''; draw(); } });
  try { top = localStorage.getItem('importtop') || top; } catch (e) { /* privates Fenster */ }

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
  // Vorgabe je Lied: gibt es das Lied schon (gleicher Interpret und Titel), erst einmal liegen lassen, sonst verschieben
  const defDo = s => s.dup ? 'skip' : 'move';
  const doOf = s => choice[s.path] || defDo(s);
  const tgtOf = s => target[s.path] != null ? target[s.path] : s.target;

  async function load() {
    $('imsg').textContent = 'Lese den Wartebereich am Musik-Rechner …';
    try {
      data = await mac('/import?top=' + encodeURIComponent(top));
      stamp = Date.now();
    } catch (e) { $('imsg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; data = null; draw(); return; }
    if (data.tops && data.tops.length && !data.tops.includes(top)) { top = data.tops.includes('U-MUSIK') ? 'U-MUSIK' : data.tops[0]; return load(); }
    // lose Dateien und Dateien in fremden Ordnern (Archiv ...): Einsortieren in die vier Kategorien (11.11.2026)
    const lo = data.loose || 0, fo = data.foreign || 0, fd = data.foreign_dirs || [];
    $('iloose').hidden = !lo && !fo;
    $('ilooset').innerHTML = [lo ? '<b>' + lo + '</b> ' + (lo === 1 ? 'Datei liegt' : 'Dateien liegen') + ' lose im Wartebereich' : '',
      fo ? '<b>' + fo + '</b> ' + (fo === 1 ? 'Datei liegt' : 'Dateien liegen') + ' in ' + (fd.length === 1 ? 'Ordner' : 'Ordnern') + ' „' + fd.map(esc).join('“, „') + '“' : ''].filter(Boolean).join(', ') +
      '. „Einsortieren“ verteilt sie auf die vier Ordner (neu, gibt es schon …), leere Ordner danach weg. Ist das Kopieren fertig?';
    $('iother').hidden = !data.other_n;
    $('iothert').textContent = data.other_n ? data.other_n + ' Datei' + (data.other_n === 1 ? '' : 'en') + ' im Ordner „nicht MP3“: hier in MP3 umwandeln, die MP3 kommt in den Wartebereich (danach „Einsortieren“), das Original in den Papierkorb.' : '';
    if (!data.other_n) $('iotherbox').hidden = true; else if (!$('iotherbox').hidden) loadOther();
    $('top').innerHTML = (data.tops || []).map(t => '<option' + (t === top ? ' selected' : '') + '>' + esc(t) + '</option>').join('');
    if (data.missing) $('imsg').innerHTML = 'Es gibt noch keinen Wartebereich: lege neben dem Musikordner einen Ordner <b>' + esc((data.dir || 'musik-import')) + '</b> an und kopiere die neuen Lieder hinein.';
    else $('imsg').textContent = (data.n ? 'Wartebereich: ' + data.dir : 'Der Wartebereich ' + data.dir + ' ist leer.') +
      (data.made && data.made.length ? ' Neu angelegt: ' + data.made.join(', ') + '.' : '');
    draw();
  }

  const curFolder = () => {
    const fs = (data && data.folders) || [];
    let fi = fs.findIndex(f => f.name === tab);
    if (fi < 0) { fi = 0; tab = fs.length ? fs[0].name : null; page = 0; }
    return fs.length ? fi : -1;
  };
  const pages = f => Math.max(1, Math.ceil(f.songs.length / PAGE));
  function shown() {
    const fi = curFolder(); if (fi < 0) return { fi, list: [] };
    const f = data.folders[fi];
    page = Math.max(0, Math.min(page, pages(f) - 1));
    return { fi, list: f.songs.slice(page * PAGE, page * PAGE + PAGE).map((s, k) => ({ s, si: page * PAGE + k })) };
  }
  function pager(f) {
    const n = f.songs.length, pg = pages(f);
    if (pg <= 1) return '';
    return '<div class="pager"><button class="pgprev"' + (page ? '' : ' disabled') + '>‹ Zurück</button><span>Seite <b>' + (page + 1) + '</b> von ' + pg +
      ' · Lieder ' + (page * PAGE + 1) + '–' + Math.min(n, page * PAGE + PAGE) + ' von ' + n + '</span><button class="pgnext"' + (page < pg - 1 ? '' : ' disabled') + '>Weiter ›</button></div>';
  }

  function draw() {
    const box = $('folders');
    if (!data || !data.folders || !data.folders.length) { box.innerHTML = ''; $('itabs').innerHTML = ''; summary(); return; }
    const { fi, list } = shown();
    $('itabs').innerHTML = data.folders.map((f, i) => '<button data-tab="' + i + '"' + (i === fi ? ' class="on"' : '') + '>' + esc(f.name || '(oberste Ebene)') + ' <span class="dim">' + f.songs.length + '</span></button>').join('');
    box.innerHTML = [data.folders[fi]].map(f => {
      const rows = list.map(({ s, si }) => {
        const d = doOf(s), t = tgtOf(s);
        const opts = [['move', 'Verschieben'], ...(s.dup ? [['replace', 'Ersetzen']] : []), ['trash', 'Papierkorb'], ['skip', 'Liegen lassen']]
          .map(([v, l]) => '<option value="' + v + '"' + (v === d ? ' selected' : '') + '>' + l + '</option>').join('');
        const dup = s.dup ? '<div class="dup"><img class="cvimg dupcv" loading="lazy" alt="" src="' + music + '/cover?p=' + encodeURIComponent(s.dup.path) + '" onerror="this.style.display=&quot;none&quot;">' + (s.klang ? '<b>Gleicher Klang</b> (' + Math.round(s.klang * 100) + ' %, anderer Name): ' + esc((s.dup.artist || '') + ' – ' + (s.dup.title || '')) + ' · ' : 'Gibt es schon: ') + esc(s.dup.path.split('/').slice(-3).join('/')) + ' · ' + mmss(s.dup.dur) + (s.dup.kbps ? ' · ' + s.dup.kbps + ' kbit/s' : '') +
          ' <button class="pb" data-pd="' + fi + ':' + si + '" title="Das vorhandene Lied vorhören">' + (playing === s.dup.path && !audio.paused ? '❚❚' : '▶') + '</button></div>' : '';
        // gleicher Titel, anderer Interpret (Wunsch 11.11.2026): die vorhandenen Lieder mit Cover, Interpret, Laenge und Vorhoeren
        const riv = (s.rivals || []).map((c, k) => '<div class="dup riv"><img class="cvimg dupcv" loading="lazy" alt="" src="' + music + '/cover?p=' + encodeURIComponent(c.path) + '" onerror="this.style.visibility=&quot;hidden&quot;">' +
          'Gleicher Titel: <b>' + esc(c.artist || '?') + '</b> – ' + esc(String(c.title || '').replace((c.artist || '') + ' - ', '')) + ' · ' + mmss(c.dur) + (c.kbps ? ' · ' + c.kbps + ' kbit/s' : '') +
          ' <span class="file">' + esc(c.path.split('/').slice(-3, -1).join('/')) + '</span>' +
          ' <button class="pb" data-pr="' + fi + ':' + si + ':' + k + '" title="Dieses vorhandene Lied vorhören">' + (playing === c.path && !audio.paused ? '❚❚' : '▶') + '</button></div>').join('');
        const ex = d === 'move' && s.exists && t === s.target ? '<div class="warn">Am Ziel liegt schon eine Datei mit dem Namen: die neue bekommt „(2)“.</div>' : '';
        return '<tr class="' + (d === 'skip' ? 'skip' : d === 'trash' ? 'trash' : '') + '">' +
          '<td><div class="cell1"><img class="cvimg" loading="lazy" alt="" src="' + music + '/cover?p=' + encodeURIComponent(s.path) + '&v=' + stamp + '" onerror="this.style.visibility=&quot;hidden&quot;"><span>' +
          '<button class="pb' + (playing === s.path ? ' on' : '') + '" data-p="' + fi + ':' + si + '" title="Vorhören">' + (playing === s.path && !audio.paused ? '❚❚' : '▶') + '</button> ' +
          '<button class="pb" data-t="' + fi + ':' + si + '" title="Tag bearbeiten">Tag</button></span></div></td>' +
          '<td><b>' + esc(s.artist || '?') + '</b> – ' + esc(s.title || s.file) + (s.grp ? '<span class="chip">' + esc(s.grp) + '</span>' : '') +
          (s.badtag ? ' <span class="chip warnchip" title="Der Titel im Tag beginnt mit einer Tracknummer oder ist gleich dem Interpreten (oft der Albumname): erst mit „Tag“ den richtigen Titel eintragen, dann stimmen Abgleich und Ziel.">⚠ Tag prüfen</span>' : '') +
          '<div class="file">' + esc(s.file) + (s.album ? ' · ' + esc(s.album) : '') + (s.genre ? ' · ' + esc(s.genre) : '') + '</div>' + dup + riv + '</td>' +
          '<td class="num">' + mmss(s.dur) + '<div class="file">' + (s.kbps ? s.kbps + ' kbit/s' : '') + '</div></td>' +
          '<td><select data-d="' + fi + ':' + si + '">' + opts + '</select></td>' +
          '<td>' + (d === 'move' || d === 'replace' ? '<input type="text" data-g="' + fi + ':' + si + '" value="' + esc(t) + '" spellcheck="false" title="Ziel im Musikordner (Ordner/…/Datei.mp3)">' + ex
            : '<span class="dim">' + (d === 'trash' ? 'kommt in den Papierkorb' : 'bleibt im Wartebereich') + '</span>') + '</td></tr>';
      }).join('');
      const all = '<select data-all="' + fi + '" title="Für alle Lieder auf dieser Seite"><option value="">Alle …</option><option value="move">alle verschieben</option>' +
        '<option value="replace">wo vorhanden: ersetzen</option><option value="trash">alle in den Papierkorb</option><option value="skip">alle liegen lassen</option><option value="def">Vorgabe</option></select>';
      return pager(f) + '<div class="fold"><div class="row" style="padding:6px 12px 0"><label>Für alle auf dieser Seite ' + all + '</label></div>' +
        '<table><colgroup><col class="c-pl"><col class="c-song"><col class="c-len"><col class="c-do"><col></colgroup>' +
        '<thead><tr><th></th><th>Lied</th><th>Länge</th><th>Was tun</th><th>Ziel im Musikordner</th></tr></thead><tbody>' + rows + '</tbody></table></div>' + pager(f);
    }).join('');
    summary();
  }

  function items() {                                 // nur die gezeigte Seite
    const out = [];
    for (const { s } of shown().list) {
      const d = doOf(s);
      if (d === 'skip') continue;
      out.push({ path: s.path, do: d, target: tgtOf(s), dup: s.dup ? s.dup.path : '' , name: (s.artist || '?') + ' – ' + (s.title || s.file) });
    }
    return out;
  }
  function summary() {
    const it = items(), c = k => it.filter(x => x.do === k).length;
    const n = data && data.n || 0, onPage = shown().list.length;
    $('isum').textContent = n ? n + ' Lieder im Wartebereich' : '';
    $('gosum').textContent = (onPage ? 'Diese Seite: ' : '') + (it.length ? [c('move') && c('move') + ' verschieben', c('replace') && c('replace') + ' ersetzen', c('trash') && c('trash') + ' in den Papierkorb'].filter(Boolean).join(', ') + ', ' + (onPage - it.length) + ' liegen lassen' : 'nichts gewählt.');
    $('bgo').disabled = busy || !it.length;
  }
  const song = k => { const [fi, si] = k.split(':').map(Number); return data.folders[fi].songs[si]; };

  function play(p, title) {
    if (playing === p && !audio.paused) { audio.pause(); draw(); return; }
    if (playing !== p) { playing = p; audio.src = music + '/audio?p=' + encodeURIComponent(p); }
    audio.play().catch(e => SM.toast('Abspielen ging nicht: ' + e.message, 4000));
    pbar.show(title);
    draw();
  }
  audio.addEventListener('pause', () => draw());
  audio.addEventListener('play', () => draw());

  $('itabs').addEventListener('click', e => {
    const b = e.target.closest('button[data-tab]'); if (!b) return;
    tab = data.folders[+b.dataset.tab].name; page = 0; draw();
  });
  $('folders').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.classList.contains('pgprev') || b.classList.contains('pgnext')) { page += b.classList.contains('pgnext') ? 1 : -1; draw(); window.scrollTo(0, 0); return; }
    if (b.dataset.p) { const s = song(b.dataset.p); play(s.path, (s.artist || '?') + ' – ' + (s.title || s.file)); }
    else if (b.dataset.pr) { const [a_, b_, k_] = b.dataset.pr.split(':'); const c = song(a_ + ':' + b_).rivals[+k_]; play(c.path, 'vorhanden (gleicher Titel): ' + (c.artist || '') + ' – ' + (c.title || '')); }
    else if (b.dataset.pd) { const s = song(b.dataset.pd); play(s.dup.path, 'vorhanden: ' + (s.dup.artist || '') + ' – ' + (s.dup.title || '')); }
    else if (b.dataset.t) {
      const s = song(b.dataset.t);
      SM.tagEdit({ path: s.path, dur: s.dur || 0 }, music, () => { setTimeout(load, 400); });   // neue Tags: Vorschlag neu rechnen
    }
  });
  $('folders').addEventListener('change', e => {
    const el = e.target;
    if (el.dataset.d) { choice[song(el.dataset.d).path] = el.value; draw(); }
    else if (el.dataset.g) { target[song(el.dataset.g).path] = el.value.trim(); summary(); }
    else if (el.dataset.all) {
      const v = el.value; if (!v) return;
      for (const { s } of shown().list) {
        if (v === 'def') delete choice[s.path];
        else if (v === 'replace') { if (s.dup) choice[s.path] = 'replace'; }
        else choice[s.path] = v;
      }
      draw();
    }
  });
  $('top').onchange = () => { top = $('top').value; try { localStorage.setItem('importtop', top); } catch (e) { /* */ } target = {}; load(); };
  $('breload').onclick = load;
  // Klang pruefen (Wunsch 11.11.2026): gleiche Musik unter anderem Namen oder mit anderer Bitrate (Chromaprint am Mac)
  let klangPoll = null, klangFound = -1, klangLoadT = 0;
  // Meldung je nach Zahl (Wunsch 12.11.2026: "0 Lieder ... sie liegen jetzt in" war verwirrend)
  const klangDone = (n, total) => 'Fertig: ' + total + ' geprüft. ' + (n === 0 ? 'Keines gibt es schon, kein gleicher Klang gefunden.'
    : n === 1 ? '1 Lied gibt es schon (gleicher Klang): es liegt jetzt im Bereich „gibt es schon“.'
    : n + ' Lieder gibt es schon (gleicher Klang): sie liegen jetzt im Bereich „gibt es schon“.');
  function klangShow(s) {
    const run = s.state === 'run';
    $('bklang').disabled = run || s.fpcalc === false; $('bklangstop').disabled = !run;   // Knoepfe bleiben an ihrem Platz (Wunsch 11.11.2026)
    $('klangt').textContent = s.fpcalc === false ? 'Am Mac fehlt Chromaprint: im Terminal „brew install chromaprint“, dann die Seite neu laden.'
      : run ? 'Prüfe ' + ((s.done || 0) + 1) + ' von ' + s.total + (s.cur ? ' · ' + s.cur : '') + (s.found ? ' · ' + s.found + ' gefunden' : '') + ' …'
      : s.state === 'ok' ? klangDone(s.found || 0, s.total || 0)
      : s.state === 'stopped' ? 'Angehalten nach ' + (s.done || 0) + ' von ' + s.total + '.' : '';
  }
  async function klangTick(first) {
    let s; try { s = await mac('/import?klang=1'); } catch (e) { return; }
    klangShow(s);
    // verschobene Lieder gleich aus "neu" nehmen (Fehlerbericht 11.11.2026: sie standen noch dort und liessen sich nicht abspielen);
    // hoechstens alle 10 s neu laden, nicht waehrend "Ausfuehren" laeuft
    if (s.state === 'run') {
      const f = s.found || 0;
      if (klangFound < 0) klangFound = f;
      else if (f !== klangFound && !busy && Date.now() - klangLoadT > 10000) { klangFound = f; klangLoadT = Date.now(); load(); }
    }
    if (s.state === 'run' && !klangPoll) klangPoll = setInterval(() => klangTick(), 2000);
    if (s.state !== 'run' && klangPoll) { clearInterval(klangPoll); klangPoll = null; if (!first) load(); }
  }
  $('bklang').onclick = async () => {
    try { klangShow(await mac('/import', { op: 'klang' })); klangTick(); } catch (e) { $('klangt').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; }
  };
  $('bklangstop').onclick = async () => { try { await mac('/import', { op: 'klang_stop' }); } catch (e) { /* */ } };
  klangTick(true);
  // Ordner "nicht MP3" (Wunsch 12.11.2026): Dateien sehen, vorhoeren, in MP3 umwandeln, Original in den Papierkorb
  let othTimer = null, other = [], othRun = false;
  const mb = n => (n / 1e6).toFixed(1).replace('.', ',') + ' MB';
  async function loadOther() {
    try { other = (await mac('/import?other=1')).files || []; } catch (e) { $('iothmsg').textContent = e.message; return; }
    const run = other.some(f => f.state === 'wait' || f.state === 'run');
    $('iotherlist').innerHTML = other.map(f => {
      const st = f.state === 'run' ? '<span class="warn">wandelt um …</span>' : f.state === 'wait' ? '<span class="warn">wartet …</span>'
        : f.state === 'ok' ? '<span class="ok">✓ MP3 im Wartebereich, Original im Papierkorb</span>' : f.state === 'err' ? '<span class="bad">' + esc(f.error) + '</span>' : '';
      const busyF = f.state === 'wait' || f.state === 'run';
      return '<tr><td><button data-oplay="' + esc(f.name) + '" title="Vorhören">' + (playing === 'o:' + f.name ? '■' : '▶') + '</button></td><td>' + esc(f.name) + '</td><td class="warn">' + mb(f.size) + '</td>' +
        '<td><button data-oconv="' + esc(f.name) + '"' + (!f.can || busyF || f.state === 'ok' ? ' disabled' : '') + '>→ MP3</button> ' +
        '<button data-otrash="' + esc(f.name) + '"' + (busyF ? ' disabled' : '') + ' title="Original in den Papierkorb">🗑 Original</button></td><td>' + (f.can ? st : '<span class="warn">diese Dateiart geht nicht</span>') + '</td></tr>';
    }).join('');
    $('bothall').disabled = !other.some(f => f.can && !f.state);
    clearTimeout(othTimer);
    // Fehlerbericht 12.11.2026: load() ruft loadOther() wieder auf, "ok" bleibt stehen -> Endlosschleife (Cover flimmerte).
    // Darum nur einmal neu laden, wenn eine Umwandlung gerade fertig wurde.
    if (run) othTimer = setTimeout(loadOther, 2000);
    else if (othRun) load();                                 // eben fertig: lose MP3 erscheint oben bei "Einsortieren"
    othRun = run;
  }
  async function othConvert(names) {
    $('iothmsg').textContent = '';
    try { await mac('/import', { op: 'other_convert', names }); othRun = true; } catch (e) { $('iothmsg').textContent = e.message; }
    loadOther();
  }
  $('bother').onclick = () => { const b = $('iotherbox'); b.hidden = !b.hidden; $('bother').textContent = b.hidden ? 'Ansehen / umwandeln' : 'Zuklappen'; if (!b.hidden) loadOther(); };
  $('bothall').onclick = () => othConvert(other.filter(f => f.can && !f.state).map(f => f.name));
  $('iotherlist').onclick = async e => {
    const c = e.target.closest('[data-oconv]'), t = e.target.closest('[data-otrash]'), pl = e.target.closest('[data-oplay]');
    if (c) othConvert([c.dataset.oconv]);
    if (pl) {
      const n = pl.dataset.oplay;
      if (playing === 'o:' + n) { audio.pause(); playing = ''; pbar.hide(); }
      else { playing = 'o:' + n; audio.src = music + '/audio?p=' + encodeURIComponent(data.dir + '/nicht MP3/' + n); audio.play().catch(() => {}); pbar.show(n); }
      loadOther();
    }
    if (t) {
      const n = t.dataset.otrash, f = other.find(x => x.name === n) || {};
      if (!await SM.ask('„' + n + '“ am ' + (await SM.hostName()) + ' in den Papierkorb legen?' + (f.state === 'ok' ? '' : String.fromCharCode(10) + 'Es gibt noch keine MP3 davon.'), undefined, 'In den Papierkorb')) return;
      try { const r = await mac('/import', { op: 'other_trash', names: [n] }); if (r.error) $('iothmsg').textContent = r.error; } catch (err) { $('iothmsg').textContent = err.message; }
      load();
    }
  };
  $('bsort').onclick = async () => {                 // lose Dateien in die Reiter einsortieren (Wunsch 10.11.2026)
    $('bsort').disabled = true;
    $('imsg').textContent = 'Vergleiche mit der Bibliothek und sortiere ein …';
    try {
      const r = await mac('/import', { op: 'sort' });
      const parts = Object.entries(r.moved || {}).map(([k, n]) => n + ' nach „' + k + '“');
      const msg = (parts.length ? 'Einsortiert: ' + parts.join(', ') + '.' : 'Nichts einsortiert.') +
        (r.removed ? ' ' + r.removed + ' leere' + (r.removed === 1 ? 'r Ordner' : ' Ordner') + ' gelöscht.' : '') +
        (r.left && r.left.length ? ' Nicht löschen ließ sich: ' + r.left.join('; ') + ' (beim nächsten Öffnen der Seite versucht sie es wieder).' : '') +
        (r.wait ? ' ' + r.wait + ' Datei' + (r.wait === 1 ? '' : 'en') + ' wurde' + (r.wait === 1 ? '' : 'n') + ' eben erst kopiert und bleibt noch liegen: in ein paar Sekunden noch einmal tippen.' : '') +
        (r.errors && r.errors.length ? ' Nicht verschoben: ' + r.errors.slice(0, 5).join('; ') : '');
      await load();
      $('imsg').textContent = msg;
    } catch (e) { $('imsg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; }
    $('bsort').disabled = false;
  };
  $('bgo').onclick = async () => {
    const it = items(); if (!it.length) return;
    const c = k => it.filter(x => x.do === k).length;
    const txt = [c('move') && c('move') + ' Lieder in den Musikordner verschieben', c('replace') && c('replace') + ' vorhandene Lieder ersetzen (die alten in den Papierkorb)',
      c('trash') && c('trash') + ' Lieder in den Papierkorb'].filter(Boolean).join(String.fromCharCode(10));
    if (!await SM.ask(txt + String.fromCharCode(10) + String.fromCharCode(10) + 'Jetzt ausführen?', undefined, 'Ausführen')) return;
    busy = true; summary();
    if (!audio.paused) audio.pause();
    $('imsg').textContent = 'Wird ausgeführt …';
    try {
      const r = await mac('/import', { op: 'apply', items: it.map(x => ({ path: x.path, do: x.do, target: x.target, dup: x.dup })) });
      $('imsg').innerHTML = '<span class="ok">Fertig: ' + r.moved + ' verschoben' + (r.replaced ? ', ' + r.replaced + ' ersetzt' : '') + (r.trashed ? ', ' + r.trashed + ' im Papierkorb' : '') + '.</span>' +
        (r.errors && r.errors.length ? ' <span class="bad">' + r.errors.length + ' gingen nicht: ' + esc(r.errors.slice(0, 5).join('; ')) + '</span>' : '') +
        (r.moved ? '<br>Jetzt in Mixxx: Bibliothek → „Bibliothek neu einlesen“. Der Light-Butler liest den Musikordner gleich von selbst neu ein.' : '');
      choice = {}; target = {}; playing = ''; pbar.hide();
      const msg = $('imsg').innerHTML;
      await load();
      $('imsg').innerHTML = msg;
    } catch (e) { $('imsg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; }
    busy = false; summary();
  };
  load();
})();
