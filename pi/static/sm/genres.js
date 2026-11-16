// Genre-Editor (Wunsch von Markus, 08.11.2026): alle Genres aus den Tags, Vorschlaege zum Zusammenlegen, Umbenennen in allen
// betroffenen MP3s, Hausliste, Genre fuellen (Interpret, Ordner, Internet) und Protokoll mit Zuruecknehmen.
// Der Mac liest und schreibt (genre_edit.py ueber den Vorhoer-Server), der Pi nimmt den Licht-Stil des Genres mit.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const STYLE = { club: 'Club', party: 'Party', rock: 'Rock', ruhig: 'Ruhig', weihnachten: 'Weihnachten', '': 'kein Stil' };
  const SRC = { interpret: ['vom Interpreten', 'g'], ordner: ['vom Ordner', 'b'], internet: ['Internet', 'b'] };
  const PER = 20;                          // Genre fuellen: 20 Lieder je Seite (Wunsch 12.11.2026)
  let neverOpen = false;   // "Nicht vorgeschlagen" aufgeklappt (Wunsch 11.11.2026: versehentlich weggeklickte zurueckholen)
  let aiSug = {}, aiBusy = false, sugOpen = new Set();   // sugOpen: Vorschlaege mit aufgeklappter Liederliste (11.11.2026)   // Claude: {Genre: {to, why}} fuer Vorschlaege ohne Ziel (11.11.2026)
  let lastSig = '', music = '', ov = null, fill = null, tab = 'genres', sel = new Set(), open = '', songs = {}, house = [], fsel = new Set(), fpage = 0, poll = null, playing = '', seeking = false;

  async function mac(q, op, body) {
    if (!music) throw new Error('Der Light-Butler erreicht den Musik-Rechner gerade nicht. Läuft dort die Mixxx-App oder der Light-Butler Helfer?');
    const r = await fetch(music + '/genres' + (q || ''), op ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ op }, body || {})) } : {});
    let d = null;
    try { d = JSON.parse(await r.text()); } catch (e) { d = null; }
    if (r.status === 404 || !d || d.state === 'off') throw new Error('Am Musik-Rechner läuft noch die alte Fassung: Helfer oder Mixxx-App neu installieren (./deploy.sh alles).');
    if (!r.ok) throw new Error(d.error || 'ging nicht (' + r.status + ')');
    return d;
  }

  // ---- Anhoeren (wie Dateien pruefen) ----
  const audio = new Audio();
  const tmss = t => { t = Math.max(0, Math.round(t || 0)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); };
  function playPath(p, name) {
    if (!music) return;
    if (playing === p) { if (audio.paused) audio.play().catch(() => {}); else audio.pause(); return; }
    playing = p;
    audio.src = music + '/audio?p=' + encodeURIComponent(p);
    audio.play().catch(err => { $('gmsg').textContent = 'Abspielen ging nicht: ' + err.message; });
    $('pt').textContent = name || p.split('/').pop();
    $('pbar').classList.add('on'); document.body.classList.add('pbon');
  }
  const pbtn = (p, name) => '<button class="pb' + (playing === p && !audio.paused ? ' on' : '') + '" data-play="' + esc(p) + '" data-name="' + esc(name) + '" title="Anhören">' + (playing === p && !audio.paused ? '❚❚' : '▶') + '</button>';
  function drawBar() {
    $('ppp').textContent = audio.paused ? '▶' : '❚❚';
    const d = audio.duration || 0;
    if (!seeking) $('ppos').value = d ? Math.round(1000 * audio.currentTime / d) : 0;
    $('ptm').textContent = tmss(audio.currentTime) + ' / ' + tmss(d);
    for (const b of document.querySelectorAll('button[data-play]')) { const on = b.dataset.play === playing && !audio.paused; b.classList.toggle('on', on); b.textContent = on ? '❚❚' : '▶'; }
  }

  // Auswahl eines Genres (Fehlerbericht 08.11.2026: die Vorschlagsliste "datalist" liess sich nicht oeffnen): echte Auswahlliste
  // mit allen Genres (Hausliste zuerst), dazu "Anderes Genre eintippen …".
  const NEW = '__neu';
  const abc = (a, b) => a.localeCompare(b, 'de', { sensitivity: 'base' });   // Wunsch 08.11.2026: Genres immer alphabetisch
  function allGenres() {
    const out = [], seen = new Set();
    for (const g of house.concat((ov ? ov.genres : []).filter(x => !x.other).map(x => x.g))) { const k = g.toLowerCase(); if (!seen.has(k)) { seen.add(k); out.push(g); } }
    return out.sort(abc);
  }
  function genreSel(attr, val, blank, skip, only) {   // skip: Genres, die nicht in die Auswahl sollen (Hausliste, 09.11.2026)
    const no = new Set((skip || []).map(g => g.toLowerCase()));   // only: nur diese (zusammenlegen mit: nur die Hausliste, 11.11.2026)
    const gs = (only && only.length ? only.slice().sort(abc) : allGenres()).filter(g => !no.has(g.toLowerCase()));
    if (val && !gs.some(g => g === val)) gs.unshift(val);
    return '<select ' + attr + '><option value="">' + esc(blank || '– Genre wählen –') + '</option>' +
      gs.map(g => '<option value="' + esc(g) + '"' + (g === val ? ' selected' : '') + '>' + esc(g) + '</option>').join('') +
      '<option value="' + NEW + '">✎ Anderes Genre eintippen …</option></select>';
  }
  function pickNew(sel) {                  // "Anderes Genre": eintippen, als Eintrag in die Auswahl
    const g = (window.prompt('Genre eintippen (höchstens 40 Zeichen, ohne ;):', '') || '').trim().slice(0, 40);
    if (!g) { sel.value = ''; return ''; }
    if (![...sel.options].some(o => o.value === g)) { const o = document.createElement('option'); o.value = g; o.textContent = g; sel.insertBefore(o, sel.options[1]); }
    sel.value = g;
    return g;
  }
  // Datei unter dem Titel (Wunsch 09.11.2026: "ich weiss ja nicht, um welches File es sich handelt"): Pfad im Musikordner
  const fileOf = p => { const s = String(p || ''), i = s.indexOf('/musik/'); return i >= 0 ? s.slice(i + 7) : s.replace(/^\/Volumes\/[^/]+\//, ''); };
  const fileLine = p => '<div class="fpath">' + esc(fileOf(p)) + '</div>';
  // Zahl = was die Suche wirklich noch fragt (schon gesuchte, "Other" und Lieder ohne Interpret/Titel nicht), 12.11.2026
  const netLabel = () => { const net = (fill && fill.net) || {}, todo = (fill && fill.net_todo) || 0;
    return net.busy ? 'Internet anhalten (' + net.done + ' von ' + net.total + ')' : 'Im Internet nachsehen' + (todo ? ' (' + todo + ' noch nicht gesucht, je 3 s)' : ' (alle schon gesucht)'); };
  const netOff = () => !!fill && !(fill.net && fill.net.busy) && !fill.net_todo;

  // ---- Laden ----
  async function load() {
    try {
      if (!music) music = ((await fetch('/api/musik/mac').then(r => r.json())) || {}).music || '';
      ov = await mac();
      house = ov.house.slice();
      $('gmsg').textContent = '';
      if (tab === 'fill') await loadFill();
      // Fehlerbericht 08.11.2026: alle 1,5 s neu aufgebaut, dabei klappte jede offene Auswahl zu. Jetzt nur bei Aenderung.
      const sig = JSON.stringify([ov.genres, ov.suggest, ov.house, ov.undo, ov.empty, ov.ready, fill && fill.items.length, fill && fill.by_src, tab]);
      if (sig !== lastSig) { lastSig = sig; draw(); } else status();
      if (tab === 'fill' && fill) { $('fnet').textContent = netLabel(); $('fnet').disabled = netOff(); }
      clearTimeout(poll);
      if ((ov.job && ov.job.state === 'run') || (ov.net && ov.net.busy) || ov.ready === false) poll = setTimeout(load, 1500);
    } catch (e) { $('gstat').textContent = e.message; }
  }
  // nach "Tag bearbeiten": Uebersicht neu und die offenen Liederlisten frisch vom Mac (sonst bliebe "Lade …" stehen, 12.11.2026)
  async function reloadOpen() {
    await load();
    const gs = new Set(open ? [open] : []);
    for (const s of ov.suggest || []) if (sugOpen.has(s.from.join('|'))) s.from.forEach(g => gs.add(g));
    for (const g of gs) { try { songs[g] = await mac('?g=' + encodeURIComponent(g)); } catch (x) { songs[g] = { songs: [], n: 0 }; } }
    drawGenres();
  }
  async function loadFill() { fill = await mac('?fill=1&samples=' + ($('fsam').checked ? 1 : 0)); }

  function status() {
    const j = ov.job;
    let s = '<b>' + ov.genres.length + '</b> Genres · <b>' + ov.total + '</b> Lieder · ' + (ov.empty ? '<a href="#" id="gempty"><b>' + ov.empty + '</b> ohne Genre</a>' +
      (ov.empty_sam ? ' (' + ov.empty_sam + ' davon in SAMPLES/TESTSAMPLES)' : '') : '<b>0</b> ohne Genre');
    const oth = Math.max(0, (ov.fill_n || 0) - ((ov.empty || 0) - (ov.empty_sam || 0)));   // "Other" (ohne Samples), zaehlt in der Datenpflege mit
    if (oth) s += ' · <a href="#" id="gother"><b>' + oth + '</b> mit „Other“</a>';
    if (j && j.state === 'run') s += ' · <b>Schreibe: ' + j.done + ' von ' + j.total + '</b> (' + esc(j.label) + ')';
    else if (j && j.state === 'done') s += ' · zuletzt: ' + esc(j.label) + ' – ' + j.ok + ' geschrieben' + (j.skip ? ', ' + j.skip + ' übersprungen (' + [j.gone ? j.gone + '× Datei fehlt auf dem Stick (Mixxx kennt sie noch)' : '', j.notmp3 ? j.notmp3 + '× keine MP3' : ''].filter(Boolean).join(', ') + ')' + (j.err ? ': ' + esc(j.err) : '') : '');
    if (ov.ready === false) s += ' · <b>Der Musik-Rechner liest gerade noch die Tags der Dateien</b> (nach einem Neustart ein paar Minuten), die Zahlen können noch alte Werte aus Mixxx enthalten';
    if (ov.net && ov.net.busy) s += ' · <b>Internet: ' + ov.net.done + ' von ' + ov.net.total + '</b>';
    $('gstat').innerHTML = s;
  }

  function draw() {
    if (!ov) return;
    status();
    for (const b of $('gtabs').querySelectorAll('button[data-t]')) b.classList.toggle('on', b.dataset.t === tab);
    ['genres', 'fill', 'house', 'hist'].forEach(t => { $('t' + t).hidden = t !== tab; });
    // Umbenennen/Zusammenlegen: Auswahl aus der Hausliste (Wunsch 11.11.2026; ohne Hausliste alle Genres)
    $('edpickbox').innerHTML = genreSel('id="edpick"', '', house.length ? 'oder aus der Hausliste wählen …' : 'oder aus der Liste wählen …', null, house);
    if (tab === 'genres') drawGenres();
    else if (tab === 'fill') drawFill();
    else if (tab === 'house') drawHouse();
    else drawHist();
  }

  // ---- Reiter Genres ----
  function drawGenres() {
    const max = Math.max(1, ...ov.genres.map(g => g.n));
    $('glh').textContent = 'Genres (' + ov.genres.length + ')' + (house.length ? ' · gelb = nicht in der Hausliste' : '');
    $('glist').innerHTML = ov.genres.slice().sort((a, b) => abc(a.g, b.g)).map(g => {
      const row = '<div class="grow"><input type="checkbox" data-sel="' + esc(g.g) + '"' + (sel.has(g.g) ? ' checked' : '') + '>' +
        '<span' + (g.house === false ? ' class="out"' : '') + '>' + SM.favHtml('genre', g.g, { cls: 'sm' }) + esc(g.g) + (g.other ? ' <span class="tag d">Sonstiges</span>' : '') + '</span>' +
        '<span class="n">' + g.n + '</span><div class="bar' + (g.other ? ' o' : '') + '" style="width:' + Math.max(2, Math.round(100 * g.n / max)) + '%"></div>' +
        '<button data-open="' + esc(g.g) + '" title="Lieder dieses Genres zeigen">' + (open === g.g ? 'zu' : 'Lieder') + '</button></div>';
      if (open !== g.g) return row;
      const s = songs[g.g];
      return row + '<div class="songs">' + (!s ? 'Lade …' : s.songs.map(x => '<div>' + pbtn(x.path, x.artist + ' - ' + x.title) + '<button class="pb" data-tagp="' + esc(x.path) + '" title="Tag bearbeiten (auch das Genre nur dieses Liedes)">Tag</button>' + aiBtn(x, g.g) + ' ' + SM.favHtml('song', x.path, { cls: 'sm' }) + esc((x.artist || '?') + ' - ' + (x.title || x.path.split('/').pop())) + fileLine(x.path) + aiLine(x) + '</div>').join('') +
        (s.n > s.songs.length ? '<div>… und ' + (s.n - s.songs.length) + ' weitere</div>' : '')) + '</div>';
    }).join('');
    const num = ov.num || [];               // Genre nur als Nummer in der Datei ("(148)" = Abstract), 09.11.2026
    const numBox = num.length ? '<div class="sug">' + num.length + ' Lied' + (num.length === 1 ? '' : 'er') + ' mit dem Genre nur als Nummer in der Datei: ' +
      [...new Set(num.map(x => x.now + ' = ' + x.want))].slice(0, 6).map(t => '<span class="chip">' + esc(t) + '</span>').join('') +
      ' <span class="why">alte Schreibweise; Mixxx zeigt den Namen, andere Programme nicht</span><div class="acts"><button id="numgo" class="primary">Namen eintragen</button></div></div>' : '';
    const noTo = ov.suggest.filter(s => !s.to).length;
    const aiBox = noTo ? '<div class="sug">' + noTo + ' Genre' + (noTo === 1 ? '' : 's') + ' ohne Vorschlag. <button id="aiall"' + (aiBusy || !house.length ? ' disabled' : '') +
      ' title="Claude bekommt deine Hausliste, diese Genres und je ein paar Beispiele (Interpret - Titel) und schlägt je ein Genre aus der Hausliste vor. Geschrieben wird erst, wenn du „Übernehmen“ tippst.">🤖 Claude fragen</button>' +
      (house.length ? '' : ' <span class="why">Dafür braucht es eine Hausliste (Reiter Hausliste).</span>') + (aiBusy ? ' <span class="why">Claude denkt nach …</span>' : '') + '</div>' : '';
    $('sugs').innerHTML = numBox + aiBox + (ov.suggest.length ? ov.suggest.map((s, i) => { const ai = !s.to && aiSug[s.from[0]]; return '<div class="sug">' + s.from.map(g => '<span class="chip">' + esc(g) + '</span>').join('') +
      (s.to ? ' → <span class="chip">' + esc(s.to) + '</span>' : '') + ' <span class="why">' + esc(s.why) + ' · ' + s.n + ' Lied' + (s.n === 1 ? '' : 'er') + '</span>' +
      sugSongs(s, i) + (ai ? '<div class="why">🤖 Claude: ' + (ai.to ? '→ <b>' + esc(ai.to) + '</b>' : 'kein Genre der Hausliste passt') + (ai.why ? ' · ' + esc(ai.why) : '') + '</div>' : '') +
      '<div class="acts">' + (s.to ? '<button data-take="' + i + '">Übernehmen</button>' : genreSel('data-rto="' + i + '"', ai && ai.to ? ai.to : '', 'zusammenlegen mit …', null, house) + '<button data-rtake="' + i + '">Übernehmen</button>' +
        '<button data-ai="' + i + '"' + (aiBusy || !house.length ? ' disabled' : '') + ' title="Nur dieses Genre an Claude">🤖</button>') +
      '<button data-sopen="' + i + '" title="Die Lieder dieser Genres zeigen: anhören, Cover, Tag bearbeiten">' + (sugOpen.has(s.from.join('|')) ? 'Lieder zu' : 'Lieder') + '</button>' +
      '<button data-never="' + i + '" title="Diese Genres nicht mehr vorschlagen (zurückholen unten bei „Nicht vorgeschlagen“)">Nicht vorschlagen</button></div></div>'; }).join('') : (num.length ? '' : '<div class="why">Keine Vorschläge, die Genres sind sauber.</div>')) + neverBox();
    if ($('aiall')) $('aiall').onclick = () => askClaude(ov.suggest.filter(s => !s.to).map(s => s.from[0]));
    if ($('numgo')) $('numgo').onclick = async () => {
      try { await mac('', 'assign', { pairs: num.map(x => [x.path, x.want]) }); SM.toast('Schreibe den Genre-Namen in ' + num.length + ' Dateien …', 3000); load(); }
      catch (e) { $('gmsg').textContent = e.message; }
    };
    drawEd();
  }
  // Claude-Knopf je Lied (Wunsch 11.11.2026): Interpret, Titel, jetziges Genre und Hausliste an Claude (ueber den Pi),
  // Vorschlag unter dem Lied, geschrieben erst mit "Eintragen". songAi[Pfad] = {busy | to, why | err}; songInfo fuer die Anfrage.
  const songAi = {}, songInfo = {};
  function aiBtn(x, g) {
    songInfo[x.path] = { artist: x.artist || '', title: x.title || x.path.split('/').pop(), genre: g != null ? g : (x.now || x.genre || '') };
    const a = songAi[x.path];
    return '<button class="pb" data-sai="' + esc(x.path) + '"' + (a && a.busy || !house.length ? ' disabled' : '') +
      ' title="' + (house.length ? 'Claude fragen, welches Genre aus deiner Hausliste zu diesem Lied passt (geschrieben wird erst mit Eintragen)' : 'Dafür braucht es eine Hausliste (Reiter Hausliste)') + '">🤖</button>';   // Beschriftung bleibt, damit nichts springt
  }
  function aiLine(x) {
    const a = songAi[x.path];
    if (!a) return '';
    if (a.busy) return '<div class="why">🤖 Claude denkt nach …</div>';
    if (a.err) return '<div class="why">🤖 ' + esc(a.err) + '</div>';
    if (a.done) return '<div class="why">🤖 „' + esc(a.to) + '“ eingetragen.</div>';
    return '<div class="why">🤖 Claude: ' + (a.to ? '→ <b>' + esc(a.to) + '</b>' : 'kein Genre der Hausliste passt sicher') + (a.why ? ' · ' + esc(a.why) : '') +
      (a.to ? ' <button class="pb" data-sput="' + esc(x.path) + '" title="Dieses Genre in die MP3 schreiben">Eintragen</button>' : '') + '</div>';
  }
  async function askSong(p) {
    const info = songInfo[p]; if (!info || (songAi[p] && songAi[p].busy)) return;
    songAi[p] = { busy: true }; draw();
    try {
      const r = await fetch('/api/sm/cmd', { method: 'POST', body: JSON.stringify({ op: 'genre_song_ai', house, songs: [info] }) });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      const s = (d.songs || [])[0] || { to: '', why: '' };
      songAi[p] = { to: s.to, why: s.why };
      const fi = fill && fill.items && fill.items.find(x => x.path === p);   // Reiter Fuellen: gleich in die Auswahl
      if (fi && s.to) { fi.want = s.to; fi.why = '🤖 ' + (s.why || 'Claude'); fsel.add(p); }
      $('gmsg').textContent = '🤖 Claude: ' + (info.artist + ' - ' + info.title) + (s.to ? ' → ' + s.to : ': kein sicherer Vorschlag') + ' (Kosten etwa ' + (d.cost_usd || 0).toFixed(3) + ' $).';
    } catch (x) { songAi[p] = { err: x.message }; }
    draw();
  }
  async function putSong(p) {
    const a = songAi[p]; if (!a || !a.to) return;
    try { await mac('', 'assign', { pairs: [[p, a.to]] }); a.done = true; SM.toast('Schreibe „' + a.to + '“ …', 2500); draw(); setTimeout(load, 1500); }
    catch (x) { a.err = x.message; draw(); }
  }

  // Nicht vorgeschlagene Genres sammeln und zurueckholen (Wunsch 11.11.2026)
  function neverBox() {
    const nv = (ov.never || []).slice().sort(abc);
    if (!nv.length) return '';
    const cnt = Object.fromEntries(ov.genres.map(g => [g.g.toLowerCase(), g.n]));
    return '<div class="sug"><button id="neverbtn" title="Genres, die du mit „Nicht vorschlagen“ weggelegt hast">' + (neverOpen ? '▾' : '▸') + ' 🚫 Nicht vorgeschlagen (' + nv.length + ')</button>' +
      (neverOpen ? '<div class="sugsongs">' + nv.map(g => '<div class="sugsong"><button class="pb" data-unnever="' + esc(g) + '" title="Dieses Genre wieder vorschlagen">Wieder vorschlagen</button><span class="chip">' + esc(g) + '</span>' +
        '<span class="why">' + (cnt[g.toLowerCase()] ? cnt[g.toLowerCase()] + ' Lied' + (cnt[g.toLowerCase()] === 1 ? '' : 'er') : 'kommt gerade in keinem Lied vor') + '</span></div>').join('') + '</div>' : '') + '</div>';
  }

  // Liederliste unter einem Vorschlag (Wunsch 11.11.2026): Cover, Anhoeren, Tag bearbeiten
  function sugSongs(s, i) {
    if (!sugOpen.has(s.from.join('|'))) return '';
    const rows = [];
    for (const g of s.from) {
      const d = songs[g];
      if (!d) { rows.push('<div class="why">Lade ' + esc(g) + ' …</div>'); continue; }
      for (const x of d.songs || []) rows.push('<div class="sugsong"><img loading="lazy" alt="" class="cvimg" src="' + music + '/cover?p=' + encodeURIComponent(x.path) + '" onerror="this.style.visibility=&quot;hidden&quot;">' +
        pbtn(x.path, (x.artist || '') + ' - ' + (x.title || '')) + '<button class="pb" data-tagp="' + esc(x.path) + '" title="Tag bearbeiten">Tag</button>' + aiBtn(x, g) +
        '<span>' + esc((x.artist || '?') + ' - ' + (x.title || x.path.split('/').pop())) + (s.from.length > 1 ? ' <span class="chip">' + esc(g) + '</span>' : '') + fileLine(x.path) + aiLine(x) + '</span></div>');
      if (d.n > (d.songs || []).length) rows.push('<div class="why">… und ' + (d.n - d.songs.length) + ' weitere</div>');
    }
    return '<div class="sugsongs">' + rows.join('') + '</div>';
  }
  // Claude fragen (11.11.2026): je Genre bis 5 Beispiele vom Mac, dann der Pi (Schluessel und Kosten dort, showman/genre_ai.py)
  async function askClaude(gs) {
    if (aiBusy || !gs.length) return;
    aiBusy = true; drawGenres();
    $('gmsg').textContent = 'Hole Beispiele und frage Claude (' + gs.length + ' Genre' + (gs.length === 1 ? '' : 's') + ') …';
    try {
      const items = [];
      for (const g of gs.slice(0, 80)) {
        if (!songs[g]) { try { songs[g] = await mac('?g=' + encodeURIComponent(g)); } catch (x) { songs[g] = { songs: [], n: 0 }; } }
        const s = songs[g];
        items.push({ g, n: s.n || (s.songs || []).length, ex: (s.songs || []).slice(0, 5).map(x => [x.artist || '', x.title || x.path.split('/').pop()]) });
      }
      const r = await fetch('/api/sm/cmd', { method: 'POST', body: JSON.stringify({ op: 'genre_ai', house, items }) });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      Object.assign(aiSug, d.map || {});
      const hit = Object.values(d.map || {}).filter(x => x.to).length;
      $('gmsg').textContent = '🤖 Claude hat für ' + hit + ' von ' + items.length + ' Genres ein Ziel vorgeschlagen (Kosten etwa ' + (d.cost_usd || 0).toFixed(3) + ' $). Prüfen und mit „Übernehmen“ anwenden.';
    } catch (x) { $('gmsg').textContent = 'Claude: ' + x.message; }
    aiBusy = false; drawGenres();
  }
  async function drawEd() {
    const gs = [...sel], to = $('edto').value.trim();
    const n = ov.genres.filter(g => sel.has(g.g) && g.g !== to).reduce((a, g) => a + g.n, 0);
    const all = ov.genres.filter(g => sel.has(g.g)).reduce((a, g) => a + g.n, 0);
    // Fehlerbericht 09.11.2026: angehakt wird der Name vorgetragen; solange er gleich bleibt, aendert sich nichts ("0 Lieder" verwirrte)
    const same = gs.length && to && !n;
    $('edsel').innerHTML = gs.length ? gs.map(g => '<span class="chip">' + esc(g) + '</span>').join('') + ' <span class="why">' + all + ' Lieder' +
      (same ? ' · <b>neuen Namen eintippen</b> (oder einen aus der Liste wählen)' : '') + '</span>' : 'Links Genres anhaken oder rechts einen Vorschlag übernehmen.';
    $('edgo').disabled = !gs.length || !to || !n || (ov.job && ov.job.state === 'run');
    $('edgo').textContent = n ? 'In ' + n + ' Dateien schreiben' : same ? 'Name ist noch gleich' : 'Schreiben';
    if (!gs.length || !to) { $('edstyle').textContent = ''; return; }
    try {
      const st = (await SM.cmd('genre_styles', { genres: gs.concat([to]) })).styles || {};
      const from = [...new Set(gs.map(g => st[g] || ''))];
      $('edstyle').innerHTML = 'Licht-Stil: ' + gs.map(g => esc(g) + ' = <b>' + STYLE[st[g] || ''] + '</b>').join(', ') +
        (from.length === 1 ? ' → ' + esc(to) + ' bekommt <b>' + STYLE[from[0]] + '</b>' + ((st[to] || '') === from[0] ? ' (wie bisher)' : ' (wird mitgenommen)')
          : ' → verschiedene Stile, ' + esc(to) + ' behält <b>' + STYLE[st[to] || ''] + '</b> (im Panel unter Stil änderbar)');
    } catch (e) { $('edstyle').textContent = ''; }
  }
  async function writeRename() {
    const gs = [...sel], to = $('edto').value.trim();
    const n = ov.genres.filter(g => sel.has(g.g) && g.g !== to).reduce((a, g) => a + g.n, 0);
    if (!await SM.ask('Genre „' + to + '“ in ' + n + ' Dateien schreiben?\n\nVorher: ' + gs.join(', ') + '\n\nNur das Genre-Feld, die Musik bleibt gleich. Im Protokoll zurücknehmbar.', undefined, 'Schreiben')) return;
    try {
      await mac('', 'rename', { from: gs, to });
      await waitJob();
      try { await SM.cmd('genre_style_carry', { from: gs, to }); } catch (e) { /* Stil bleibt dann, wie er ist */ }
      sel.clear(); $('edto').value = ''; songs = {}; open = '';
      SM.toast('Fertig. Mixxx: Datenpflege → Geänderte Tags', 4000);
    } catch (e) { $('gmsg').textContent = e.message; }
    load();
  }
  async function waitJob() {
    for (;;) {
      ov = await mac(); status();
      if (!ov.job || ov.job.state !== 'run') return;
      await new Promise(r => setTimeout(r, 800));
    }
  }

  // ---- Reiter Genre fuellen ----
  function fitems() {
    const s = $('fsrc').value, nw = $('fnow').value;                 // nw: nur ohne Genre / nur Other (Wunsch 09.11.2026)
    return !fill ? [] : fill.items.filter(x => (!s || (x.src || 'keiner') === s) && (!nw || (nw === 'leer' ? !x.now : !!x.now)));
  }
  function fgoUpdate() {                                   // Schreiben-Knopf: bleibt unten sichtbar, an festem Platz (Wunsch 12.11.2026)
    $('fgo').textContent = 'Angehakte schreiben (' + fsel.size + ')';
    $('fgo').disabled = !fsel.size;
    if ($('fnone')) $('fnone').disabled = !fsel.size;
    $('fgohint').textContent = fsel.size ? '' : 'Lieder anhaken (oder oben „Alle dieser Seite mit Vorschlag anhaken“), dann hier schreiben.';
  }
  // Wunsch 12.11.2026: die Knoepfe oben wirken nur auf die gezeigte Seite (hoechstens PER Lieder), nicht auf alle Seiten
  const pageItems = () => { const arr = fitems(); return arr.slice(fpage * PER, fpage * PER + PER); };
  function drawFill() {
    if (!fill) { $('flist').innerHTML = '<div class="why">Lade …</div>'; return; }
    const b = fill.by_src || {};
    const noSug = b.keiner || 0;
    const nOther = fill.items.filter(x => x.now).length;
    $('fsum').innerHTML = '<b>' + (fill.n - nOther) + '</b> Lieder ohne Genre' + (nOther ? ' (dazu ' + nOther + ' mit „Other“, gilt als vergeben)' : '') + ($('fsam').checked ? '' : ', ohne Samples') + ' · Vorschläge: ' +
      (b.interpret || 0) + ' vom Interpreten, ' + (b.ordner || 0) + ' vom Ordner, ' + (b.internet || 0) + ' aus dem Internet, ' + noSug + ' ohne.';
    const net = fill.net || {};
    $('fnet').textContent = netLabel(); $('fnet').disabled = netOff();
    const arr = fitems(), pages = Math.max(1, Math.ceil(arr.length / PER));
    fpage = Math.min(fpage, pages - 1);
    const cur = arr.slice(fpage * PER, fpage * PER + PER);
    const pager = arr.length > PER ? '<div class="pager"><button data-fpg="-1"' + (fpage ? '' : ' disabled') + '>‹</button> Seite <b>' + (fpage + 1) + '</b> von <b>' + pages + '</b> <button data-fpg="1"' + (fpage < pages - 1 ? '' : ' disabled') + '>›</button></div>' : '';
    fgoUpdate();
    $('fnone').disabled = !fsel.size;
    // Genre fuellen: in den Auswahlen nur die Hausliste (Wunsch 12.11.2026), ein Vorschlag ausserhalb steht trotzdem oben
    if (!$('fsetbox').firstChild || $('fsetbox').dataset.h !== house.join('|')) { $('fsetbox').innerHTML = genreSel('id="fsetg"', '', null, null, house); $('fsetbox').dataset.h = house.join('|'); }
    $('fset').textContent = 'Allen ' + cur.length + ' dieser Seite eintragen und anhaken';
    $('fall').textContent = 'Alle dieser Seite mit Vorschlag anhaken (' + cur.filter(x => x.want).length + ')';
    $('flist').innerHTML = !arr.length ? '<div class="why">Nichts zu füllen.</div>' : pager + cur.map(x => {
      const s = SRC[x.src];
      // Zeile (Wunsch 12.11.2026): Haken, ▶, Cover, Titel, jetzt, Vorschlag (Auswahl + 🤖 in einer Zelle, Grund und Claude darunter)
      return '<div class="frow"><input type="checkbox" data-fsel="' + esc(x.path) + '"' + (fsel.has(x.path) ? ' checked' : '') + '>' + pbtn(x.path, x.artist + ' - ' + x.title) +
        '<img class="fcv cvimg" loading="lazy" alt="" src="' + music + '/cover?p=' + encodeURIComponent(x.path) + '" onerror="this.style.visibility=&quot;hidden&quot;">' +
        '<span class="t">' + esc((x.artist || '?') + ' - ' + (x.title || x.path.split('/').pop())) + fileLine(x.path) + '</span>' +
        '<span class="now">' + esc(x.now || 'leer') + '</span>' +
        '<span class="w"><span class="wsel">' + genreSel('data-fw="' + esc(x.path) + '"', x.want, null, null, house) + aiBtn(x, x.now || '') + '</span>' +
        ((s || x.house === false) ? '<span class="wtags">' + (s ? '<span class="tag ' + s[1] + '">' + s[0] + '</span>' : '') + (x.house === false ? '<span class="tag">nicht in der Hausliste</span>' : '') + '</span>' : '') +
        (x.why ? '<div class="why">' + esc(x.why) + '</div>' : '') + aiLine(x) + '</span></div>';
    }).join('') + pager;
  }
  async function writeFill() {
    const want = {};
    for (const x of fill.items) want[x.path] = x.want;
    for (const i of $('flist').querySelectorAll('select[data-fw]')) if (i.value !== NEW) want[i.dataset.fw] = i.value.trim();
    const pairs = [...fsel].map(p => [p, want[p] || '']).filter(x => x[1]);
    if (!pairs.length) { $('gmsg').textContent = 'Nichts angehakt (oder ohne Genre).'; return; }
    if (!await SM.ask(pairs.length + ' Lieder bekommen das eingetragene Genre. Schreiben?', undefined, 'Schreiben')) return;
    try {
      await mac('', 'assign', { pairs });
      await waitJob();
      fsel.clear();
      SM.toast('Fertig. Mixxx: Datenpflege → Geänderte Tags', 4000);
      await loadFill();
    } catch (e) { $('gmsg').textContent = e.message; }
    load();
  }

  // ---- Reiter Hausliste ----
  function drawHouse() {
    house.sort(abc);
    $('hpickbox').innerHTML = genreSel('id="hpick"', '', 'Genre hinzufügen …', house);   // nur, was noch fehlt
    $('hchips').innerHTML = house.length ? house.map((g, i) => '<span class="hchip">' + esc(g) + '<button data-hdel="' + i + '" title="Aus der Hausliste">✕</button></span>').join('') : '<span class="why">Noch keine Hausliste.</span>';
  }

  // ---- Reiter Protokoll ----
  function drawHist() {
    const h = ov.undo || [];
    $('hlist').innerHTML = !h.length ? '<div class="why">Noch nichts geschrieben.</div>' : h.map(x => '<div class="hist"><span class="why">' +
      new Date(x.t * 1000).toLocaleString('de-AT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + '</span><span>' + esc(x.label) + '</span><span class="why">' + x.n + ' Dat.</span>' +
      (x.undone ? '<span class="tag d">zurückgenommen</span>' : x.kind === 'undo' ? '<span></span>' : '<button data-undo="' + esc(x.id) + '">Zurücknehmen</button>') + '</div>').join('');
  }

  // ---- Ereignisse ----
  $('gtabs').onclick = async e => {
    const b = e.target.closest('button[data-t]'); if (!b) return;
    tab = b.dataset.t; draw();
    if (tab === 'fill' && !fill) { try { await loadFill(); draw(); } catch (x) { $('gmsg').textContent = x.message; } }
  };
  document.body.addEventListener('click', e => {      // Claude-Knopf je Lied (11.11.2026)
    const sa = e.target.closest('button[data-sai]'); if (sa) { askSong(sa.dataset.sai); return; }
    const sp = e.target.closest('button[data-sput]'); if (sp) putSong(sp.dataset.sput);
  });
  document.body.addEventListener('click', async e => {
    const pl = e.target.closest('button[data-play]');
    if (pl) { playPath(pl.dataset.play, pl.dataset.name); return; }
    const op = e.target.closest('button[data-open]');
    if (op) {
      const g = op.dataset.open;
      open = open === g ? '' : g; drawGenres();
      if (open && !songs[g]) { try { songs[g] = await mac('?g=' + encodeURIComponent(g)); } catch (x) { $('gmsg').textContent = x.message; } drawGenres(); }
      return;
    }
    const so = e.target.closest('button[data-sopen]');
    if (so) {
      const s = ov.suggest[+so.dataset.sopen], k = s.from.join('|');
      if (sugOpen.has(k)) sugOpen.delete(k); else sugOpen.add(k);
      drawGenres();
      for (const g of s.from) if (!songs[g]) { try { songs[g] = await mac('?g=' + encodeURIComponent(g)); } catch (x) { songs[g] = { songs: [], n: 0 }; } }
      drawGenres();
      return;
    }
    const tp = e.target.closest('button[data-tagp]');
    if (tp) { SM.tagEdit({ path: tp.dataset.tagp, dur: 0 }, music, () => { songs = {}; setTimeout(reloadOpen, 500); }); return; }
    const ab = e.target.closest('button[data-ai]');
    if (ab) { askClaude([ov.suggest[+ab.dataset.ai].from[0]]); return; }
    const tk = e.target.closest('button[data-take]');
    if (tk) { const s = ov.suggest[+tk.dataset.take]; sel = new Set(s.from); $('edto').value = s.to; drawGenres(); $('ed').scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
    const rt = e.target.closest('button[data-rtake]');
    if (rt) {
      const i = +rt.dataset.rtake, s = ov.suggest[i], v = ($('sugs').querySelector('select[data-rto="' + i + '"]') || {}).value || '';
      if (!v || v === NEW) { $('gmsg').textContent = 'Erst ein Genre zum Zusammenlegen wählen.'; return; }
      sel = new Set(s.from); $('edto').value = v.trim(); drawGenres(); $('ed').scrollIntoView({ behavior: 'smooth', block: 'center' }); return;
    }
    if (e.target.closest('#neverbtn')) { neverOpen = !neverOpen; drawGenres(); return; }
    const unv = e.target.closest('button[data-unnever]');
    if (unv) { try { await mac('', 'never', { g: unv.dataset.unnever, on: false }); SM.toast('„' + unv.dataset.unnever + '“ wird wieder vorgeschlagen', 2500); } catch (x) { $('gmsg').textContent = x.message; } load(); return; }
    const nv = e.target.closest('button[data-never]');
    if (nv) { try { for (const g of ov.suggest[+nv.dataset.never].from) await mac('', 'never', { g, on: true }); } catch (x) { $('gmsg').textContent = x.message; } load(); return; }
    const un = e.target.closest('button[data-undo]');
    if (un) {
      const h = (ov.undo || []).find(x => x.id === un.dataset.undo);
      if (!h || !await SM.ask('„' + h.label + '“ zurücknehmen? ' + h.n + ' Dateien bekommen ihr altes Genre wieder.', undefined, 'Zurücknehmen')) return;
      try { await mac('', 'undo', { id: h.id }); await waitJob(); SM.toast('Zurückgenommen.', 2500); } catch (x) { $('gmsg').textContent = x.message; }
      load(); return;
    }
    const hd = e.target.closest('button[data-hdel]');
    if (hd) { house.splice(+hd.dataset.hdel, 1); drawHouse(); return; }
    const fp = e.target.closest('button[data-fpg]');
    if (fp) { fpage += +fp.dataset.fpg; drawFill(); window.scrollTo(0, 0); }
  });
  document.body.addEventListener('change', e => {
    const c = e.target.closest('input[data-sel]');
    if (c) { if (c.checked) sel.add(c.dataset.sel); else sel.delete(c.dataset.sel); if (c.checked && !$('edto').value) { $('edto').value = c.dataset.sel; $('edto').focus(); $('edto').select(); } drawEd(); return; }
    const f = e.target.closest('input[data-fsel]');
    if (f) { if (f.checked) fsel.add(f.dataset.fsel); else fsel.delete(f.dataset.fsel); fgoUpdate(); return; }
    const w = e.target.closest('select[data-fw]');
    if (w && fill) {
      const v = w.value === NEW ? pickNew(w) : w.value.trim();
      const it = fill.items.find(x => x.path === w.dataset.fw); if (it) it.want = v;
      const box = $('flist').querySelector('input[data-fsel="' + CSS.escape(w.dataset.fw) + '"]');
      if (v) fsel.add(w.dataset.fw); else fsel.delete(w.dataset.fw);
      if (box) box.checked = !!v;
      fgoUpdate();
      return;
    }
    const rs = e.target.closest('select[data-rto]');
    if (rs && rs.value === NEW) { pickNew(rs); return; }
    const es = e.target.closest('#edpick');
    if (es) { const v = es.value === NEW ? pickNew(es) : es.value; if (v) { $('edto').value = v; drawEd(); } es.value = ''; return; }
    const hs = e.target.closest('#hpick');
    if (hs) { const v = hs.value === NEW ? pickNew(hs) : hs.value; if (v && !house.some(x => x.toLowerCase() === v.toLowerCase())) house.push(v); hs.value = ''; drawHouse(); }
  });
  $('edto').addEventListener('input', () => drawEd());
  $('edclr').onclick = () => { sel.clear(); $('edto').value = ''; drawGenres(); };
  $('edgo').onclick = writeRename;
  $('fsam').onchange = async () => { fpage = 0; try { await loadFill(); } catch (x) { $('gmsg').textContent = x.message; } drawFill(); };
  $('fsrc').onchange = () => { fpage = 0; drawFill(); };
  $('fnow').onchange = () => { fpage = 0; drawFill(); };
  $('fset').onclick = () => {                     // allen gezeigten dasselbe Genre (etwa "Sample"), geschrieben wird erst mit "Angehakte schreiben"
    const sg = $('fsetg'); if (!sg) return;
    const g = sg.value === NEW ? pickNew(sg) : sg.value.trim();
    if (!g) { $('gmsg').textContent = 'Erst ein Genre wählen.'; return; }
    for (const x of pageItems()) { x.want = g; fsel.add(x.path); }
    drawFill();
  };
  document.addEventListener('click', async e => {   // "213 ohne Genre": gleich die Lieder zeigen, auch die Samples
    const ge = e.target.closest('#gempty'), go = e.target.closest('#gother');
    if (!ge && !go) return;
    e.preventDefault();
    tab = 'fill'; $('fnow').value = ge ? 'leer' : 'other'; $('fsrc').value = ''; fpage = 0;
    if (ge && ov && ov.empty_sam && !$('fsam').checked) { $('fsam').checked = true; fill = null; }
    draw();
    if (!fill) { try { await loadFill(); } catch (x) { $('gmsg').textContent = x.message; } draw(); }
  });
  $('fall').onclick = () => { for (const x of pageItems()) if (x.want) fsel.add(x.path); drawFill(); };
  $('fnone').onclick = () => { fsel.clear(); drawFill(); };   // alle Haken weg (Wunsch 12.11.2026), auch auf anderen Seiten
  $('fgo').onclick = writeFill;
  $('fnet').onclick = async () => {
    try {
      if (fill && fill.net && fill.net.busy) await mac('', 'net_stop');
      else await mac('', 'net_start', { samples: $('fsam').checked });
      await loadFill(); drawFill(); load();
    } catch (x) { $('gmsg').textContent = x.message; }
  };

  $('hsug').onclick = async () => { try { house = (await mac('', 'house_suggest')).house; drawHouse(); } catch (x) { $('gmsg').textContent = x.message; } };
  $('hsave').onclick = async () => { try { house = (await mac('', 'house', { genres: house })).house; SM.toast('Hausliste gespeichert (' + house.length + ' Genres)', 2500); load(); } catch (x) { $('gmsg').textContent = x.message; } };
  let vol = 80;
  try { vol = Math.max(0, Math.min(100, parseInt(localStorage.getItem('musikvol') || '80', 10) || 0)); } catch (e) { /* privat */ }
  $('vol').value = vol; audio.volume = vol / 100;
  $('vol').addEventListener('input', () => { audio.volume = $('vol').value / 100; try { localStorage.setItem('musikvol', $('vol').value); } catch (e) { /* privat */ } });
  ['timeupdate', 'play', 'pause', 'loadedmetadata'].forEach(ev => audio.addEventListener(ev, drawBar));
  audio.addEventListener('playing', () => { if (/^Abspielen ging nicht/.test($('gmsg').textContent)) $('gmsg').textContent = ''; });   // alte Meldung weg
  $('ppos').addEventListener('input', () => { seeking = true; });
  $('ppos').addEventListener('change', () => { const d = audio.duration || 0; if (d) audio.currentTime = d * $('ppos').value / 1000; seeking = false; });
  $('ppp').onclick = () => { if (playing) playPath(playing); };
  $('pcl').onclick = () => { audio.pause(); playing = ''; $('pbar').classList.remove('on'); document.body.classList.remove('pbon'); drawBar(); };
  const tq = new URLSearchParams(location.search).get('t');   // aus der Datenpflege: gleich der passende Reiter
  if (['genres', 'fill', 'house', 'hist'].includes(tq)) tab = tq;
  SM.favLoad();                                          // Herzen (Favoriten, 14.11.2026): Lieblings-Genres
  load();
})();
