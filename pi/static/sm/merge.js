// Ordner aufloesen (Wunsch 10.11.2026): einen Oberordner (OLDIES) in einen anderen (U-MUSIK) einsortieren. Der Mac liest die
// Lieder (GET /merge), schlaegt das Ziel vor und verschiebt ueber die Warteschlange fuer Mixxx (POST /merge,
// mac/mixxx_bridge/folder_merge.py). Vorhoeren mit der Leiste unten, Tags mit "Tag bearbeiten", Seiten zu 20 Liedern.
(() => {
  const $ = id => document.getElementById(id), esc = SM.esc;
  const mmss = s => s ? Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0') : '';
  const audio = new Audio();
  const PAGE = 20;
  let music = '', data = null, playing = '', choice = {}, target = {}, busy = false, page = 0, stamp = Date.now();
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
  const defDo = s => s.dup ? 'skip' : 'move';
  const doOf = s => choice[s.path] || defDo(s);
  const tgtOf = s => target[s.path] != null ? target[s.path] : s.target;

  async function load() {
    const src = $('src').value, dst = $('dst').value;
    $('mmsg').textContent = src ? 'Lese ' + src + ' am Musik-Rechner …' : 'Lese die Ordner …';
    try {
      data = await mac('/merge?src=' + encodeURIComponent(src || '') + '&dst=' + encodeURIComponent(dst || ''));
      stamp = Date.now();
    } catch (e) { $('mmsg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; data = null; draw(); return; }
    const tp = data.tops || [];
    const keep = (sel, v, def) => { sel.innerHTML = '<option value="">– wählen –</option>' + tp.map(t => '<option' + (t === (v || def) ? ' selected' : '') + '>' + esc(t) + '</option>').join(''); };
    keep($('src'), data.src || src, '');
    keep($('dst'), data.dst || dst, tp.includes('U-MUSIK') ? 'U-MUSIK' : '');
    if (!$('grp').value || $('grp').dataset.auto === '1') { $('grp').value = data.src || ''; $('grp').dataset.auto = '1'; }
    $('mmsg').textContent = !data.src ? 'Ordner zum Auflösen und Ziel wählen.' : data.n ? data.n + ' Lieder in ' + data.src + '.' : 'In ' + data.src + ' liegen keine Lieder (mehr).';
    draw();
  }

  const songs = () => (data && data.songs) || [];
  const pages = () => Math.max(1, Math.ceil(songs().length / PAGE));
  function shown() {
    page = Math.max(0, Math.min(page, pages() - 1));
    return songs().slice(page * PAGE, page * PAGE + PAGE).map((s, k) => ({ s, si: page * PAGE + k }));
  }
  function pager() {
    const n = songs().length, pg = pages();
    if (pg <= 1) return '';
    return '<div class="pager"><button class="pgprev"' + (page ? '' : ' disabled') + '>‹ Zurück</button><span>Seite <b>' + (page + 1) + '</b> von ' + pg +
      ' · Lieder ' + (page * PAGE + 1) + '–' + Math.min(n, page * PAGE + PAGE) + ' von ' + n + '</span><button class="pgnext"' + (page < pg - 1 ? '' : ' disabled') + '>Weiter ›</button></div>';
  }

  function draw() {
    const list = shown();
    if (!list.length) { $('list').innerHTML = ''; summary(); return; }
    const rows = list.map(({ s, si }) => {
      const d = doOf(s), t = tgtOf(s);
      const opts = [['move', 'Verschieben'], ...(s.dup ? [['replace', 'Ersetzen']] : []), ['trash', 'Papierkorb'], ['skip', 'Liegen lassen']]
        .map(([v, l]) => '<option value="' + v + '"' + (v === d ? ' selected' : '') + '>' + l + '</option>').join('');
      const dup = s.dup ? '<div class="dup"><img class="cvimg dupcv" loading="lazy" alt="" src="' + music + '/cover?p=' + encodeURIComponent(s.dup.path) + '" onerror="this.style.display=&quot;none&quot;">Gibt es schon: ' +
        esc(s.dup.path.split('/').slice(-3).join('/')) + ' · ' + mmss(s.dup.dur) + (s.dup.kbps ? ' · ' + s.dup.kbps + ' kbit/s' : '') +
        ' <button class="pb" data-pd="' + si + '" title="Das vorhandene Lied vorhören">' + (playing === s.dup.path && !audio.paused ? '❚❚' : '▶') + '</button></div>' : '';
      const ex = d === 'move' && s.exists && t === s.target ? '<div class="warn">Am Ziel liegt schon eine Datei mit dem Namen: diese bekommt „(2)“.</div>' : '';
      return '<tr class="' + (d === 'skip' ? 'skip' : d === 'trash' ? 'trash' : '') + '">' +
        '<td><div class="cell1"><img class="cvimg" loading="lazy" alt="" src="' + music + '/cover?p=' + encodeURIComponent(s.path) + '&v=' + stamp + '" onerror="this.style.visibility=&quot;hidden&quot;"><span>' +
        '<button class="pb' + (playing === s.path ? ' on' : '') + '" data-p="' + si + '" title="Vorhören">' + (playing === s.path && !audio.paused ? '❚❚' : '▶') + '</button> ' +
        '<button class="pb" data-t="' + si + '" title="Tag bearbeiten">Tag</button></span></div></td>' +
        '<td><b>' + esc(s.artist || '?') + '</b> – ' + esc(s.title || s.rel) + (s.grp ? '<span class="chip">' + esc(s.grp) + '</span>' : '') +
        '<div class="file">' + esc(s.rel) + (s.album ? ' · ' + esc(s.album) : '') + (s.genre ? ' · ' + esc(s.genre) : '') + '</div>' + dup + '</td>' +
        '<td class="num">' + mmss(s.dur) + '<div class="file">' + (s.kbps ? s.kbps + ' kbit/s' : '') + '</div></td>' +
        '<td><select data-d="' + si + '">' + opts + '</select></td>' +
        '<td>' + (d === 'move' || d === 'replace' ? '<input type="text" data-g="' + si + '" value="' + esc(t) + '" spellcheck="false" title="Ziel im Musikordner (Ordner/…/Datei.mp3)">' + ex
          : '<span class="dim">' + (d === 'trash' ? 'kommt in den Papierkorb' : 'bleibt, wo es ist') + '</span>') + '</td></tr>';
    }).join('');
    const all = '<select data-all="1" title="Für alle Lieder auf dieser Seite"><option value="">Alle …</option><option value="move">alle verschieben</option>' +
      '<option value="replace">wo vorhanden: ersetzen</option><option value="trash">alle in den Papierkorb</option><option value="skip">alle liegen lassen</option><option value="def">Vorgabe</option></select>';
    $('list').innerHTML = pager() + '<div class="fold"><div class="row" style="padding:6px 12px 0"><label>Für alle auf dieser Seite ' + all + '</label></div>' +
      '<table><colgroup><col class="c-pl"><col class="c-song"><col class="c-len"><col class="c-do"><col></colgroup>' +
      '<thead><tr><th></th><th>Lied</th><th>Länge</th><th>Was tun</th><th>Ziel im Musikordner</th></tr></thead><tbody>' + rows + '</tbody></table></div>' + pager();
    summary();
  }
  function items() {
    return shown().map(({ s }) => ({ s, d: doOf(s) })).filter(x => x.d !== 'skip')
      .map(({ s, d }) => ({ path: s.path, file: s.file, do: d, target: tgtOf(s), dup: s.dup ? s.dup.path : '' }));
  }
  function summary() {
    const it = items(), c = k => it.filter(x => x.do === k).length, onPage = shown().length;
    $('msum').textContent = data && data.n ? data.n + ' Lieder im Ordner' : '';
    $('gosum').textContent = onPage ? 'Diese Seite: ' + (it.length ? [c('move') && c('move') + ' verschieben', c('replace') && c('replace') + ' ersetzen', c('trash') && c('trash') + ' in den Papierkorb'].filter(Boolean).join(', ') + ', ' + (onPage - it.length) + ' liegen lassen' : 'nichts gewählt.') : '';
    $('bgo').disabled = busy || !it.length;
  }
  function play(p, title) {
    if (playing === p && !audio.paused) { audio.pause(); draw(); return; }
    if (playing !== p) { playing = p; audio.src = music + '/audio?p=' + encodeURIComponent(p); }
    audio.play().catch(e => SM.toast('Abspielen ging nicht: ' + e.message, 4000));
    pbar.show(title);
    draw();
  }
  audio.addEventListener('pause', () => draw());
  audio.addEventListener('play', () => draw());

  $('list').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.classList.contains('pgprev') || b.classList.contains('pgnext')) { page += b.classList.contains('pgnext') ? 1 : -1; draw(); window.scrollTo(0, 0); return; }
    const s = songs()[+(b.dataset.p || b.dataset.pd || b.dataset.t)];
    if (!s) return;
    if (b.dataset.p) play(s.path, (s.artist || '?') + ' – ' + (s.title || ''));
    else if (b.dataset.pd) play(s.dup.path, 'vorhanden: ' + (s.dup.artist || '') + ' – ' + (s.dup.title || ''));
    else if (b.dataset.t) SM.tagEdit({ path: s.path, dur: s.dur || 0 }, music, () => { setTimeout(load, 400); });
  });
  $('list').addEventListener('change', e => {
    const el = e.target;
    if (el.dataset.d) { choice[songs()[+el.dataset.d].path] = el.value; draw(); }
    else if (el.dataset.g) { target[songs()[+el.dataset.g].path] = el.value.trim(); summary(); }
    else if (el.dataset.all) {
      const v = el.value; if (!v) return;
      for (const { s } of shown()) {
        if (v === 'def') delete choice[s.path];
        else if (v === 'replace') { if (s.dup) choice[s.path] = 'replace'; }
        else choice[s.path] = v;
      }
      draw();
    }
  });
  $('src').onchange = () => { choice = {}; target = {}; page = 0; $('grp').dataset.auto = '1'; $('grp').value = ''; load(); };
  $('dst').onchange = () => { target = {}; load(); };
  $('grp').oninput = () => { $('grp').dataset.auto = '0'; };
  $('breload').onclick = load;
  $('bgo').onclick = async () => {
    const it = items(); if (!it.length || !data) return;
    const c = k => it.filter(x => x.do === k).length, NL = String.fromCharCode(10);
    const grp = $('grpon').checked ? $('grp').value.trim() : '';
    const txt = [c('move') && c('move') + ' Lieder nach ' + data.dst + ' verschieben', c('replace') && c('replace') + ' vorhandene Lieder ersetzen (die alten in den Papierkorb)',
      c('trash') && c('trash') + ' Lieder in den Papierkorb', grp && 'Gruppe „' + grp + '“ eintragen, wo sie fehlt'].filter(Boolean).join(NL);
    if (!await SM.ask(txt + NL + NL + 'Mixxx übernimmt die neuen Pfade beim nächsten Start der App „Light-Butler Mixxx“. Jetzt ausführen?', undefined, 'Ausführen')) return;
    busy = true; summary();
    if (!audio.paused) audio.pause();
    $('mmsg').textContent = 'Wird ausgeführt …';
    try {
      const r = await mac('/merge', { op: 'apply', src: data.src, group: grp, items: it });
      const msg = '<span class="ok">Fertig: ' + r.moved + ' verschoben' + (r.replaced ? ', ' + r.replaced + ' ersetzt' : '') + (r.trashed ? ', ' + r.trashed + ' im Papierkorb' : '') +
        (r.grouped ? ', bei ' + r.grouped + ' die Gruppe eingetragen' : '') + (r.removed_dirs ? ', ' + r.removed_dirs + ' leere Ordner entfernt' : '') + '.</span>' +
        (r.errors && r.errors.length ? ' <span class="bad">' + r.errors.length + ' gingen nicht: ' + esc(r.errors.slice(0, 5).join('; ')) + '</span>' : '') +
        (r.moved ? '<br>Mixxx übernimmt die neuen Pfade beim nächsten Start der App „Light-Butler Mixxx“ (bis dahin in Mixxx nicht „Bibliothek neu einlesen“).' : '');
      choice = {}; target = {}; playing = ''; pbar.hide();
      await load();
      $('mmsg').innerHTML = msg;
    } catch (e) { $('mmsg').innerHTML = '<span class="bad">' + esc(e.message) + '</span>'; }
    busy = false; summary();
  };
  $('grp').dataset.auto = '1';
  load();
})();
